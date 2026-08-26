package model

import (
	"time"
)

// ChatLab format constants
const (
	ChatLabTypeText     = 0
	ChatLabTypeImage    = 1
	ChatLabTypeVoice    = 2
	ChatLabTypeVideo    = 3
	ChatLabTypeFile     = 4
	ChatLabTypeEmoji    = 5
	ChatLabTypeLink     = 7
	ChatLabTypeLocation = 8

	ChatLabTypeRedPacket = 20
	ChatLabTypeTransfer  = 21
	ChatLabTypePoke      = 22
	ChatLabTypeCall      = 23
	ChatLabTypeShare     = 24
	ChatLabTypeReply     = 25
	ChatLabTypeForward   = 26
	ChatLabTypeContact   = 27

	ChatLabTypeSystem = 80
	ChatLabTypeRecall = 81
	ChatLabTypeOther  = 99
)

type ChatLab struct {
	ChatLab  ChatLabHeader    `json:"chatlab"`
	Meta     ChatLabMeta      `json:"meta"`
	Members  []ChatLabMember  `json:"members"`
	Messages []ChatLabMessage `json:"messages"`
}

type ChatLabHeader struct {
	Version     string `json:"version"`
	ExportedAt  int64  `json:"exportedAt"`
	Generator   string `json:"generator,omitempty"`
	Description string `json:"description,omitempty"`
}

type ChatLabMeta struct {
	Name        string `json:"name"`
	Platform    string `json:"platform"`
	Type        string `json:"type"`
	GroupID     string `json:"groupId,omitempty"`
	GroupAvatar string `json:"groupAvatar,omitempty"`
}

type ChatLabMember struct {
	PlatformID    string   `json:"platformId"`
	AccountName   string   `json:"accountName"`
	GroupNickname string   `json:"groupNickname,omitempty"`
	Aliases       []string `json:"aliases,omitempty"`
	Avatar        string   `json:"avatar,omitempty"`
}

type ChatLabMessage struct {
	Sender        string `json:"sender"`
	AccountName   string `json:"accountName"`
	GroupNickname string `json:"groupNickname,omitempty"`
	Timestamp     int64  `json:"timestamp"`
	Type          int    `json:"type"`
	Content       string `json:"content"`
}

// ConvertToChatLab converts a slice of internal Messages to ChatLab format
func ConvertToChatLab(messages []*Message, talkerID string, talkerName string) ChatLab {
	cl := ChatLab{
		ChatLab: ChatLabHeader{
			Version:    "0.0.1",
			ExportedAt: time.Now().Unix(),
			Generator:  "Chatlog",
		},
		Meta: ChatLabMeta{
			Name:     talkerName,
			Platform: "wechat",
			Type:     "private",
		},
		Members:  make([]ChatLabMember, 0),
		Messages: make([]ChatLabMessage, 0, len(messages)),
	}

	if talkerName == "" {
		cl.Meta.Name = talkerID
	}

	// Infer chat type
	isGroup := false
	if len(talkerID) > 9 && talkerID[len(talkerID)-9:] == "@chatroom" {
		cl.Meta.Type = "group"
		cl.Meta.GroupID = talkerID
		isGroup = true
	}

	memberMap := make(map[string]ChatLabMember)

	for _, msg := range messages {
		// Map Message Type
		clType := ChatLabTypeText
		content := msg.Content

		// Refine Content and Type
		switch msg.Type {
		case MessageTypeText:
			clType = ChatLabTypeText
		case MessageTypeImage:
			clType = ChatLabTypeImage
			if path, ok := msg.Contents["path"].(string); ok {
				content = path
			} else if md5, ok := msg.Contents["md5"].(string); ok {
				content = md5
			} else {
				content = "[图片]"
			}
		case MessageTypeVoice:
			clType = ChatLabTypeVoice
			content = "[语音]"
		case MessageTypeVideo:
			clType = ChatLabTypeVideo
			content = "[视频]"
		case MessageTypeAnimation:
			clType = ChatLabTypeEmoji
			if cdnURL, ok := msg.Contents["cdnurl"].(string); ok {
				content = cdnURL
			} else {
				content = "[表情]"
			}
		case MessageTypeLocation:
			clType = ChatLabTypeLocation
			label, _ := msg.Contents["label"].(string)
			if label != "" {
				content = label
			} else {
				content = "[位置]"
			}
		case MessageTypeCard:
			clType = ChatLabTypeContact
			content = "[名片]"
		case MessageTypeVOIP:
			clType = ChatLabTypeCall
			content = "[通话]"
		case MessageTypeSystem:
			clType = ChatLabTypeSystem
		case MessageTypeShare:
			// Default share type
			clType = ChatLabTypeShare
			
			switch msg.SubType {
			case MessageSubTypeFile:
				clType = ChatLabTypeFile
				if title, ok := msg.Contents["title"].(string); ok {
					content = title
				}
			case MessageSubTypeLink, MessageSubTypeLink2:
				clType = ChatLabTypeLink
				if url, ok := msg.Contents["url"].(string); ok {
					content = url
				}
			case MessageSubTypeMergeForward, MessageSubTypeNote, MessageSubTypeChatRoomNotice:
				clType = ChatLabTypeForward
				if title, ok := msg.Contents["title"].(string); ok {
					content = title
				}
			case MessageSubTypeMiniProgram, MessageSubTypeMiniProgram2:
				clType = ChatLabTypeShare
				if title, ok := msg.Contents["title"].(string); ok {
					content = title
				}
			case MessageSubTypeQuote:
				clType = ChatLabTypeReply
				// In ChatLab, content is the reply text. 
				// Structure for reply is usually just text, but maybe with some ref?
				// Spec says 25 is REPLY.
				// We keep the text content as is.
			case MessageSubTypePat:
				clType = ChatLabTypePoke
			case MessageSubTypeMusic:
				clType = ChatLabTypeShare
				if url, ok := msg.Contents["url"].(string); ok {
					content = url
				}
			case MessageSubTypePay:
				clType = ChatLabTypeTransfer
			case MessageSubTypeRedEnvelope, MessageSubTypeRedEnvelopeCover:
				clType = ChatLabTypeRedPacket
				content = "[红包]"
			}
		default:
			clType = ChatLabTypeOther
		}

		// Handle Self Name
		senderName := msg.SenderName
		if msg.IsSelf && senderName == "" {
			senderName = "我"
		}

		clMsg := ChatLabMessage{
			Sender:      msg.Sender,
			AccountName: senderName,
			Timestamp:   msg.Time.Unix(),
			Type:        clType,
			Content:     content,
		}

		// For groups, we might have group nicknames. 
		// Internal model has 'SenderName' which is usually the display name in chat (Remark or NickName).
		// In WeChat, the 'Remark' is personal to the observer, 'NickName' is global. 
		// Group Alias is specific to the room. 
		// Our 'SenderName' logic in db/message might already be mixing these. 
		// We'll map SenderName to AccountName for now.
		if isGroup {
			clMsg.GroupNickname = senderName // Assume SenderName is the display name in group
		}

		cl.Messages = append(cl.Messages, clMsg)

		// Collect Member
		if _, exists := memberMap[msg.Sender]; !exists {
			member := ChatLabMember{
				PlatformID:  msg.Sender,
				AccountName: senderName,
			}
			if isGroup {
				member.GroupNickname = senderName
			}
			memberMap[msg.Sender] = member
		}
	}

	for _, m := range memberMap {
		cl.Members = append(cl.Members, m)
	}

	return cl
}