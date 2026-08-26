package mcp

const (
	JsonRPCVersion = "2.0"
)

// Documents: https://modelcontextprotocol.io/docs/concepts/transports

// Request
//
//	{
//		jsonrpc: "2.0",
//		id: number | string,
//		method: string,
//		params?: object
//	}
type Request struct {
	JsonRPC string      `json:"jsonrpc"`
	ID      interface{} `json:"id"`
	Method  string      `json:"method"`
	Params  interface{} `json:"params,omitempty"`
}

// Response
//
//	{
//		jsonrpc: "2.0",
//		id: number | string,
//		result?: object,
//		error?: {
//			code: number,
//			message: string,
//			data?: unknown
//		}
//	}
type Response struct {
	JsonRPC string      `json:"jsonrpc"`
	ID      interface{} `json:"id"`
	Result  interface{} `json:"result,omitempty"`
	Error   *Error      `json:"error,omitempty"`
}

func NewResponse(id interface{}, result interface{}) *Response {
	return &Response{
		JsonRPC: JsonRPCVersion,
		ID:      id,
		Result:  result,
	}
}

// Notifications
//
//	{
//		jsonrpc: "2.0",
//		method: string,
//		params?: object
//	}
type Notification struct {
	JsonRPC string      `json:"jsonrpc"`
	Method  string      `json:"method"`
	Params  interface{} `json:"params,omitempty"`
}
