# This Dockerfile is used only for development purposes.
# sms-proxy is not deployed as a container in production.

FROM golang:1.21-alpine AS builder

WORKDIR /app
COPY go.mod go.sum ./
RUN go mod download

COPY . .
RUN GOOS=linux GOARCH=amd64 go build -o sms-proxy .

FROM alpine:latest
RUN apk --no-cache add ca-certificates
WORKDIR /root/

COPY --from=builder /app/sms-proxy .

EXPOSE 8000

CMD ["sh", "-c", "./sms-proxy -port 8000 -private-ip $PRIVATE_IP"]