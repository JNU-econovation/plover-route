# GraphHopper 최신 공식 배포본을 사용하는 안정적인 Dockerfile
FROM eclipse-temurin:21-jre-alpine

# GraphHopper 최신 버전 지정
ENV GH_VERSION=9.1
ENV JAVA_OPTS="-Xmx2g -Xms2g"

RUN apk add --no-cache wget curl bash \
    && mkdir -p /app/graph-cache /app/custom_areas /app/map-data \
    && wget -O /app/graphhopper-web.jar https://repo1.maven.org/maven2/com/graphhopper/graphhopper-web/${GH_VERSION}/graphhopper-web-${GH_VERSION}.jar

WORKDIR /app

COPY config.yml /app/config.yml
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

EXPOSE 8989
ENTRYPOINT ["/app/entrypoint.sh"]
