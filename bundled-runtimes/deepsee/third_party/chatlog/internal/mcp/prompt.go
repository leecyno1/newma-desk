package mcp

// Document: https://modelcontextprotocol.io/docs/concepts/prompts

const (
	// Client => Server
	MethodPromptsList = "prompts/list"
	MethodPromptsGet  = "prompts/get"
)

// Prompt
//
//	{
//		name: string;              // Unique identifier for the prompt
//		description?: string;      // Human-readable description
//		arguments?: [              // Optional list of arguments
//			{
//				name: string;          // Argument identifier
//				description?: string;  // Argument description
//				required?: boolean;    // Whether argument is required
//			}
//		]
//	}
type Prompt struct {
	Name        string           `json:"name"`
	Description string           `json:"description,omitempty"`
	Arguments   []PromptArgument `json:"arguments,omitempty"`
}

type PromptArgument struct {
	Name        string `json:"name"`
	Description string `json:"description,omitempty"`
	Required    bool   `json:"required,omitempty"`
}

// ListPrompts
//
//	{
//		prompts: [
//			{
//				name: "analyze-code",
//				description: "Analyze code for potential improvements",
//				arguments: [
//					{
//						name: "language",
//						description: "Programming language",
//						required: true
//					}
//				]
//			}
//		]
//	}
type PromptsListResponse struct {
	Prompts []Prompt `json:"prompts"`
}

// Use Prompt
// Request
//
//	{
//		method: "prompts/get",
//		params: {
//			name: "analyze-code",
//			arguments: {
//				language: "python"
//			}
//		}
//	}
//
// Response
//
//	{
//		description: "Analyze Python code for potential improvements",
//		messages: [
//			{
//				role: "user",
//				content: {
//					type: "text",
//					text: "Please analyze the following Python code for potential improvements:\n\n```python\ndef calculate_sum(numbers):\n    total = 0\n    for num in numbers:\n        total = total + num\n    return total\n\nresult = calculate_sum([1, 2, 3, 4, 5])\nprint(result)\n```"
//				}
//			}
//		]
//	}
type PromptsGetRequest struct {
	Name      string `json:"name"`
	Arguments M      `json:"arguments"`
}

type PromptsGetResponse struct {
	Description string          `json:"description"`
	Messages    []PromptMessage `json:"messages"`
}

type PromptMessage struct {
	Role    string        `json:"role"`
	Content PromptContent `json:"content"`
}

type PromptContent struct {
	Type     string      `json:"type"`
	Text     string      `json:"text,omitempty"`
	Resource interface{} `json:"resource,omitempty"` // Resource or ResourceTemplate
}

// {
// 	"messages": [
// 		{
// 			"role": "user",
// 			"content": {
// 				"type": "text",
// 				"text": "Analyze these system logs and the code file for any issues:"
// 			}
// 		},
// 		{
// 			"role": "user",
// 			"content": {
// 				"type": "resource",
// 				"resource": {
// 					"uri": "logs://recent?timeframe=1h",
// 					"text": "[2024-03-14 15:32:11] ERROR: Connection timeout in network.py:127\n[2024-03-14 15:32:15] WARN: Retrying connection (attempt 2/3)\n[2024-03-14 15:32:20] ERROR: Max retries exceeded",
// 					"mimeType": "text/plain"
// 				}
// 			}
// 		},
// 		{
// 			"role": "user",
// 			"content": {
// 				"type": "resource",
// 				"resource": {
// 					"uri": "file:///path/to/code.py",
// 					"text": "def connect_to_service(timeout=30):\n    retries = 3\n    for attempt in range(retries):\n        try:\n            return establish_connection(timeout)\n        except TimeoutError:\n            if attempt == retries - 1:\n                raise\n            time.sleep(5)\n\ndef establish_connection(timeout):\n    # Connection implementation\n    pass",
// 					"mimeType": "text/x-python"
// 				}
// 			}
// 		}
// 	]
// }
