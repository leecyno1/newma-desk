package mcp

import (
	"fmt"
	"time"

	"github.com/gin-gonic/gin"
)

const (
	SSEPingIntervalS  = 30
	SSEMessageChanCap = 100
	SSEContentType    = "text/event-stream; charset=utf-8"
)

type SSEWriter struct {
	id string
	c  *gin.Context
}

func NewSSEWriter(c *gin.Context, id string) *SSEWriter {
	c.Writer.Header().Set("Content-Type", SSEContentType)
	c.Writer.Header().Set("Cache-Control", "no-cache")
	c.Writer.Header().Set("Connection", "keep-alive")
	c.Writer.Header().Set("Access-Control-Allow-Origin", "*")
	c.Writer.Flush()

	w := &SSEWriter{
		id: id,
		c:  c,
	}
	w.WriteEndpoing()
	go w.ping()
	return w
}

func (w *SSEWriter) Write(p []byte) (n int, err error) {
	w.WriteMessage(string(p))
	return len(p), nil
}

func (w *SSEWriter) WriteMessage(data string) {
	w.WriteEvent("message", data)
}

func (w *SSEWriter) WriteEvent(event string, data string) {
	w.c.Writer.WriteString(fmt.Sprintf("event: %s\n", event))
	w.c.Writer.WriteString(fmt.Sprintf("data: %s\n\n", data))
	w.c.Writer.Flush()
}

func (w *SSEWriter) ping() {
	for {
		select {
		case <-time.After(time.Second * SSEPingIntervalS):
			w.writePing()
		case <-w.c.Request.Context().Done():
			return
		}
	}
}

// WriteEndpoing
// event: endpoint
// data: /message?sessionId=285d67ee-1c17-40d9-ab03-173d5ff48419
func (w *SSEWriter) WriteEndpoing() {
	w.c.Writer.WriteString(fmt.Sprintf("event: endpoint\n"))
	w.c.Writer.WriteString(fmt.Sprintf("data: /message?sessionId=%s\n\n", w.id))
	w.c.Writer.Flush()
}

// WritePing
// : ping - 2025-03-16 06:41:51.280928+00:00
func (w *SSEWriter) writePing() {
	w.c.Writer.WriteString(fmt.Sprintf(": ping - %s\n\n", time.Now().Format("2006-01-02 15:04:05.999999-07:00")))
}

// SSE Session
// 维持一个 SSE 连接的会话
// 会话中包含了 SSE 连接的 ID，事件通道，停止通道
// 事件通道用于发送事件，停止通道用于停止会话
// 需要轮询发送 ping 事件以保持连接
type SSESession struct {
	SessionID string
	Events    map[string]chan string
	Stop      chan bool

	c *gin.Context
}

func NewSSESession(c *gin.Context) *SSESession {
	return &SSESession{c: c}
}
func (s *SSESession) SendEvent(event string, data string) {
	s.c.SSEvent(event, data)
}

func (s *SSESession) Close() {
	close(s.Stop)
}

// Event
// request:
//   POST /messages?sesessionId=?
//   '{"method":"prompts/list","params":{},"jsonrpc":"2.0","id":3}'
//
// response:
//   GET /sse
//   event: message
//   data: {"jsonrpc":"2.0","id":3,"result":{"prompts":[]}}

// {
// 	"jsonrpc": "2.0",
// 	"id": 1,
// 	"result": {
// 	  "tools": [
// 		{
// 		  "name": "get_alerts",
// 		  "description": "Get weather alerts for a US state.\n\n    Args:\n        state: Two-letter US state code (e.g. CA, NY)\n    ",
// 		  "inputSchema": {
// 			"properties": {
// 			  "state": {
// 				"title": "State",
// 				"type": "string"
// 			  }
// 			},
// 			"required": [
// 			  "state"
// 			],
// 			"title": "get_alertsArguments",
// 			"type": "object"
// 		  }
// 		},
// 		{
// 		  "name": "get_forecast",
// 		  "description": "Get weather forecast for a location.\n\n    Args:\n        latitude: Latitude of the location\n        longitude: Longitude of the location\n    ",
// 		  "inputSchema": {
// 			"properties": {
// 			  "latitude": {
// 				"title": "Latitude",
// 				"type": "number"
// 			  },
// 			  "longitude": {
// 				"title": "Longitude",
// 				"type": "number"
// 			  }
// 			},
// 			"required": [
// 			  "latitude",
// 			  "longitude"
// 			],
// 			"title": "get_forecastArguments",
// 			"type": "object"
// 		  }
// 		}
// 	  ]
// 	}
//   }

// PING
