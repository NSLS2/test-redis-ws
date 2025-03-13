docker run --net=host --rm -v ./redis:/usr/local/etc/redis --name test-redis redis redis-server /usr/local/etc/redis/redis.conf
