package main

import (
    "context"
    "encoding/hex"
    "encoding/json"
    "fmt"
    "math/rand"
    "net/http"
    "os"
    "strconv"
    "strings"
    "time"

    "github.com/gin-gonic/gin"
    "github.com/gorilla/websocket"
    "github.com/nats-io/nats.go"
)

type Settings struct {
    NatsURL  string
    KvBucket string
    TTL      time.Duration
}

type AppState struct {
    Nc *nats.Conn
    Js nats.JetStreamContext
    Kv nats.KeyValue
}

type Metadata struct {
    Timestamp   string `json:"timestamp"`
    ContentType string `json:"Content-Type,omitempty"`
    Reason      string `json:"reason,omitempty"`
}

type DataValue struct {
    Metadata Metadata `json:"metadata"`
    Payload  string   `json:"payload"` // hex string
}

var upgrader = websocket.Upgrader{}

func main() {
    settings := Settings{
        NatsURL:  "nats://localhost:4222",
        KvBucket: "datasets",
        TTL:      time.Hour,
    }

    nc, err := nats.Connect(settings.NatsURL)
    if err != nil {
        panic(err)
    }
    js, err := nc.JetStream()
    if err != nil {
        panic(err)
    }
    kv, err := js.KeyValue(settings.KvBucket)
    if err != nil {
        _, err = js.CreateKeyValue(&nats.KeyValueConfig{
            Bucket:  settings.KvBucket,
            History: 1,
            TTL:     settings.TTL,
        })
        if err != nil {
            panic(err)
        }
        kv, err = js.KeyValue(settings.KvBucket)
        if err != nil {
            panic(err)
        }
    }

    state := &AppState{Nc: nc, Js: js, Kv: kv}

    r := gin.Default()

    r.Use(func(c *gin.Context) {
        c.Writer.Header().Set("X-Server-Host", hostname())
        c.Next()
    })

    r.POST("/upload", func(c *gin.Context) {
        nodeID := rand.Intn(1_000_000)
        seqKey := fmt.Sprintf("seq_num.%d", nodeID)
        _, err := state.Kv.Create(seqKey, []byte("0"))
        if err != nil {
            c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
            return
        }
        c.JSON(http.StatusOK, gin.H{"node_id": nodeID})
    })

    r.DELETE("/upload/:node_id", func(c *gin.Context) {
        nodeID := c.Param("node_id")
        seqKey := fmt.Sprintf("seq_num.%s", nodeID)
        err := state.Kv.Delete(seqKey)
        if err != nil {
            c.Status(http.StatusInternalServerError)
            return
        }
        c.Status(http.StatusNoContent)
    })

    r.POST("/upload/:node_id", func(c *gin.Context) {
        nodeID := c.Param("node_id")
        seqKey := fmt.Sprintf("seq_num.%s", nodeID)
        entry, err := state.Kv.Get(seqKey)
        seqNum := 0
        if err == nil {
            seqNum, _ = strconv.Atoi(string(entry.Value()))
        }
        seqNum++
        state.Kv.Put(seqKey, []byte(strconv.Itoa(seqNum)))

        binaryData, _ := c.GetRawData()
        metadata := Metadata{
            Timestamp:   time.Now().Format(time.RFC3339),
            ContentType: c.GetHeader("Content-Type"),
        }
        dataKey := fmt.Sprintf("data.%s.%d", nodeID, seqNum)
        value := DataValue{
            Metadata: metadata,
            Payload:  hex.EncodeToString(binaryData),
        }
        valBytes, _ := json.Marshal(value)
        state.Kv.Put(dataKey, valBytes)
        state.Nc.Publish(fmt.Sprintf("notify.%s", nodeID), []byte(strconv.Itoa(seqNum)))
        c.Status(http.StatusOK)
    })

    r.POST("/close/:node_id", func(c *gin.Context) {
        nodeID := c.Param("node_id")
        seqKey := fmt.Sprintf("seq_num.%s", nodeID)
        entry, err := state.Kv.Get(seqKey)
        seqNum := 0
        if err == nil {
            seqNum, _ = strconv.Atoi(string(entry.Value()))
        }
        seqNum++
        state.Kv.Put(seqKey, []byte(strconv.Itoa(seqNum)))

        var body map[string]interface{}
        c.BindJSON(&body)
        reason := ""
        if r, ok := body["reason"].(string); ok {
            reason = r
        }
        metadata := Metadata{
            Timestamp:   time.Now().Format(time.RFC3339),
            ContentType: c.GetHeader("Content-Type"),
            Reason:      reason,
        }
        dataKey := fmt.Sprintf("data.%s.%d", nodeID, seqNum)
        value := DataValue{
            Metadata: metadata,
            Payload:  "",
        }
        valBytes, _ := json.Marshal(value)
        state.Kv.Put(dataKey, valBytes)
        state.Nc.Publish(fmt.Sprintf("notify.%s", nodeID), []byte(strconv.Itoa(seqNum)))
        c.JSON(http.StatusOK, gin.H{
            "status": fmt.Sprintf("Connection for node %s is now closed.", nodeID),
            "reason": reason,
        })
    })

    r.GET("/stream/live", func(c *gin.Context) {
        keys, _ := state.Kv.Keys()
        nodes := []string{}
        for _, key := range keys {
            if strings.HasPrefix(key, "seq_num.") {
                parts := strings.Split(key, ".")
                if len(parts) > 1 {
                    nodes = append(nodes, parts[1])
                }
            }
        }
        c.JSON(http.StatusOK, nodes)
    })

    r.GET("/stream/single/:node_id", func(c *gin.Context) {
        nodeID := c.Param("node_id")
        conn, err := upgrader.Upgrade(c.Writer, c.Request, nil)
        if err != nil {
            return
        }
        defer conn.Close()

        seqKey := fmt.Sprintf("seq_num.%s", nodeID)
        entry, err := state.Kv.Get(seqKey)
        currentSeq := 0
        if err == nil {
            currentSeq, _ = strconv.Atoi(string(entry.Value()))
        }

        ctx, cancel := context.WithCancel(context.Background())
        defer cancel()

        sub, _ := state.Nc.SubscribeSync(fmt.Sprintf("notify.%s", nodeID))
        defer sub.Unsubscribe()

        // Replay old data
        for s := 1; s <= currentSeq; s++ {
            sendDataOverWS(state, conn, nodeID, s)
        }

        // Listen for new data
        for {
            msg, err := sub.NextMsgWithContext(ctx)
            if err != nil {
                break
            }
            seq, _ := strconv.Atoi(string(msg.Data))
            sendDataOverWS(state, conn, nodeID, seq)
        }
    })

    r.Run(":8000")
}

func sendDataOverWS(state *AppState, conn *websocket.Conn, nodeID string, seqNum int) {
    dataKey := fmt.Sprintf("data.%s.%d", nodeID, seqNum)
    entry, err := state.Kv.Get(dataKey)
    if err != nil {
        return
    }
    var value DataValue
    json.Unmarshal(entry.Value(), &value)
    resp := map[string]interface{}{
        "sequence":    seqNum,
        "metadata":    value.Metadata,
        "payload":     value.Payload,
        "server_host": hostname(),
    }
    conn.WriteJSON(resp)
}

func hostname() string {
    h, _ := os.Hostname()
    return h
}