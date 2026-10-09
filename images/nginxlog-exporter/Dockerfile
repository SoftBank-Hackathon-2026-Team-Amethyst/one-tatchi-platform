# Rebuild the unchanged upstream release with a patched Go toolchain.
# The upstream v1.11.0 image still embeds Go 1.18.10.
FROM golang:1.27.2-alpine AS build
ENV CGO_ENABLED=0
RUN go install github.com/martin-helmich/prometheus-nginxlog-exporter@v1.11.0

FROM scratch
COPY --from=build /go/bin/prometheus-nginxlog-exporter /exporter
COPY --from=build /go/pkg/mod/github.com/martin-helmich/prometheus-nginxlog-exporter@v1.11.0/LICENSE /LICENSE
USER 65534:65534
EXPOSE 4040
ENTRYPOINT ["/exporter"]
