package mcp

// Document: https://modelcontextprotocol.io/docs/concepts/tools

const (
	// Client => Server
	MethodToolsList = "tools/list"
	MethodToolsCall = "tools/call"
)

type M map[string]interface{}

// Tool
//
//	{
//		name: string;          // Unique identifier for the tool
//		description?: string;  // Human-readable description
//		inputSchema: {         // JSON Schema for the tool's parameters
//			type: "object",
//			properties: { ... }  // Tool-specific parameters
//		}
//	}
//
//	{
//		name: "analyze_csv",
//		description: "Analyze a CSV file",
//		inputSchema: {
//			type: "object",
//			properties: {
//				filepath: { type: "string" },
//				operations: {
//					type: "array",
//					items: {
//						enum: ["sum", "average", "count"]
//					}
//				}
//			}
//		}
//	}
//
//	{
//		"jsonrpc": "2.0",
//		"id": 1,
//		"result": {
//		  "tools": [
//			{
//			  "name": "get_alerts",
//			  "description": "Get weather alerts for a US state.\n\n    Args:\n        state: Two-letter US state code (e.g. CA, NY)\n    ",
//			  "inputSchema": {
//				"properties": {
//				  "state": {
//					"title": "State",
//					"type": "string"
//				  }
//				},
//				"required": [
//				  "state"
//				],
//				"title": "get_alertsArguments",
//				"type": "object"
//			  }
//			},
//			{
//			  "name": "get_forecast",
//			  "description": "Get weather forecast for a location.\n\n    Args:\n        latitude: Latitude of the location\n        longitude: Longitude of the location\n    ",
//			  "inputSchema": {
//				"properties": {
//				  "latitude": {
//					"title": "Latitude",
//					"type": "number"
//				  },
//				  "longitude": {
//					"title": "Longitude",
//					"type": "number"
//				  }
//				},
//				"required": [
//				  "latitude",
//				  "longitude"
//				],
//				"title": "get_forecastArguments",
//				"type": "object"
//			  }
//			}
//		  ]
//		}
//	  }
type Tool struct {
	Name        string     `json:"name"`
	Description string     `json:"description,omitempty"`
	InputSchema ToolSchema `json:"inputSchema"`
}

type ToolSchema struct {
	Type       string   `json:"type"`
	Properties M        `json:"properties"`
	Required   []string `json:"required,omitempty"`
}

//	{
//		"method": "tools/call",
//		"params": {
//		  "name": "chatlog",
//		  "arguments": {
//			"start": "2006-11-12",
//			"end": "2020-11-20",
//			"limit": "50",
//			"offset": "6"
//		  },
//		  "_meta": {
//			"progressToken": 1
//		  }
//		},
//		"jsonrpc": "2.0",
//		"id": 3
//	  }
type ToolsCallRequest struct {
	Name      string `json:"name"`
	Arguments M      `json:"arguments"`
}

//	{
//		"jsonrpc": "2.0",
//		"id": 2,
//		"result": {
//		  "content": [
//			{
//			  "type": "text",
//			  "text": "\nEvent: Winter Storm Warning\n"
//			}
//		  ],
//		  "isError": false
//		}
//	  }
type ToolsCallResponse struct {
	Content []Content `json:"content"`
	IsError bool      `json:"isError"`
}

type Content struct {
	Type string `json:"type"`
	Text string `json:"text"`
}
