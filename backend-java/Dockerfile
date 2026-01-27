    # 使用支持 Java 21 的 Maven 镜像进行构建
    FROM maven:3.9.6-eclipse-temurin-21 AS build
    WORKDIR /app
    COPY . .
    RUN mvn clean package -DskipTests

    # 运行环境也使用 Java 21
    FROM eclipse-temurin:21-jre-jammy
    WORKDIR /app
    COPY --from=build /app/target/*.jar app.jar
    EXPOSE 8080
    ENTRYPOINT ["java", "-jar", "app.jar"]