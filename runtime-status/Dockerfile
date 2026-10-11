FROM node:22-alpine
RUN apk upgrade --no-cache
WORKDIR /app
COPY --chown=1000:1000 src ./src
USER 1000:1000
EXPOSE 8080
CMD ["node", "src/server.mjs"]
