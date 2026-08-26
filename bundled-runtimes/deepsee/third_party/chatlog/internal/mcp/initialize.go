package mcp

const (
	MethodInitialize = "initialize"
	MethodPing       = "ping"
	ProtocolVersion  = "2024-11-05"
)

//	{
//		"method": "initialize",
//		"params": {
//		  "protocolVersion": "2024-11-05",
//		  "capabilities": {
//			"sampling": {},
//			"roots": {
//			  "listChanged": true
//			}
//		  },
//		  "clientInfo": {
//			"name": "mcp-inspector",
//			"version": "0.0.1"
//		  }
//		},
//		"jsonrpc": "2.0",
//		"id": 0
//	  }
type InitializeRequest struct {
	ProtocolVersion string      `json:"protocolVersion"`
	Capabilities    M           `json:"capabilities"`
	ClientInfo      *ClientInfo `json:"clientInfo"`
}

type ClientInfo struct {
	Name    string `json:"name"`
	Version string `json:"version"`
}

//	{
//		"jsonrpc": "2.0",
//		"id": 0,
//		"result": {
//		  "protocolVersion": "2024-11-05",
//		  "capabilities": {
//			"experimental": {},
//			"prompts": {
//			  "listChanged": false
//			},
//			"resources": {
//			  "subscribe": false,
//			  "listChanged": false
//			},
//			"tools": {
//			  "listChanged": false
//			}
//		  },
//		  "serverInfo": {
//			"name": "weather",
//			"version": "1.4.1"
//		  }
//		}
//	  }
type InitializeResponse struct {
	ProtocolVersion string     `json:"protocolVersion"`
	Capabilities    M          `json:"capabilities"`
	ServerInfo      ServerInfo `json:"serverInfo"`
}

type ServerInfo struct {
	Name    string `json:"name"`
	Version string `json:"version"`
}

var DefaultCapabilities = M{
	"experimental": M{},
	"prompts":      M{"listChanged": false},
	"resources":    M{"subscribe": false, "listChanged": false},
	"tools":        M{"listChanged": false},
}
