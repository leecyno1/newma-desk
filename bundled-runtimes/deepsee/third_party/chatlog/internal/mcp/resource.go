package mcp

// Document: https://modelcontextprotocol.io/docs/concepts/resources

const (
	// Client => Server
	MethodResourcesList         = "resources/list"
	MethodResourcesTemplateList = "resources/templates/list"
	MethodResourcesRead         = "resources/read"
	MethodResourcesSubscribe    = "resources/subscribe"
	MethodResourcesUnsubscribe  = "resources/unsubscribe"

	// Server => Client
	NotificationResourcesListChanged = "notifications/resources/list_changed"
	NofiticationResourcesUpdated     = "notifications/resources/updated"
)

// Direct resources
//
//	{
//		uri: string;           // Unique identifier for the resource
//		name: string;          // Human-readable name
//		description?: string;  // Optional description
//		mimeType?: string;     // Optional MIME type
//	}
type Resource struct {
	URI         string `json:"uri"`
	Name        string `json:"name"`
	Description string `json:"description,omitempty"`
	MimeType    string `json:"mimeType,omitempty"`
}

// Resource templates
//
//	{
//		uriTemplate: string;   // URI template following RFC 6570
//		name: string;          // Human-readable name for this type
//		description?: string;  // Optional description
//		mimeType?: string;     // Optional MIME type for all matching resources
//	}
type ResourceTemplate struct {
	URITemplate string `json:"uriTemplate"`
	Name        string `json:"name"`
	Description string `json:"description,omitempty"`
	MimeType    string `json:"mimeType,omitempty"`
}

// Reading resources
// {
// 	contents: [
// 		{
// 			uri: string;        // The URI of the resource
// 			mimeType?: string;  // Optional MIME type

//				// One of:
//				text?: string;      // For text resources
//				blob?: string;      // For binary resources (base64 encoded)
//			}
//		]
//	}
type ReadingResource struct {
	Contents []ReadingResourceContent `json:"contents"`
}

type ResourcesReadRequest struct {
	URI string `json:"uri"`
}

type ReadingResourceContent struct {
	URI      string `json:"uri"`
	MimeType string `json:"mimeType,omitempty"`
	Text     string `json:"text,omitempty"`
	Blob     string `json:"blob,omitempty"`
}
