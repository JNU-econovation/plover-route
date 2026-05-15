FROM eclipse-temurin:21-jdk-jammy AS builder
WORKDIR /app

COPY build.gradle settings.gradle gradlew ./
COPY gradle ./gradle
RUN chmod +x gradlew

RUN --mount=type=cache,target=/root/.gradle ./gradlew dependencies --no-daemon

COPY src ./src
RUN --mount=type=cache,target=/root/.gradle ./gradlew bootJar --no-daemon

WORKDIR /app/extracted
RUN java -Djarmode=layertools -jar /app/build/libs/*.jar extract

FROM eclipse-temurin:21-jre-jammy
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd -r -g 1000 spring && useradd -r -u 1000 -g spring spring
RUN mkdir -p /app/data /app/target/gwangju-routing-graph-cache \
    && chown -R spring:spring /app
USER spring

COPY --from=builder /app/extracted/dependencies/ ./
COPY --from=builder /app/extracted/spring-boot-loader/ ./
COPY --from=builder /app/extracted/snapshot-dependencies/ ./
COPY --from=builder /app/extracted/application/ ./


ENV JAVA_OPTS="-XX:MaxRAMPercentage=65.0"

EXPOSE 8989

ENTRYPOINT ["sh", "-c", "java $JAVA_OPTS org.springframework.boot.loader.launch.JarLauncher"]
