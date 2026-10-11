FROM node:22-alpine
RUN apk upgrade --no-cache \
    && rm -rf /usr/local/lib/node_modules /opt/yarn-* \
    && rm -f /usr/local/bin/npm /usr/local/bin/npx /usr/local/bin/corepack \
      /usr/local/bin/yarn /usr/local/bin/yarnpkg
WORKDIR /app
COPY --chown=1000:1000 src ./src
USER 1000:1000
EXPOSE 8080
CMD ["node", "src/server.mjs"]
