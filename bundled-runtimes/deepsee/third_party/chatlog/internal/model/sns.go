package model

import (
	"encoding/json"
	"fmt"
	"html"
	"regexp"
	"strconv"
	"strings"
	"time"
)

// SNSPost 朋友圈帖子
type SNSPost struct {
	TID         int64     `json:"tid"`
	UserName    string    `json:"user_name"`
	NickName    string    `json:"nickname"`
	CreateTime  int64     `json:"create_time"`
	CreateTimeStr string  `json:"create_time_str"`
	ContentDesc string    `json:"content_desc"`
	ContentType string    `json:"content_type"` // image, video, article, finder, text
	Location    *SNSLocation `json:"location,omitempty"`
	MediaList   []SNSMedia `json:"media_list,omitempty"`
	Article     *SNSArticle `json:"article,omitempty"`
	FinderFeed  *SNSFinderFeed `json:"finder_feed,omitempty"`
	XMLContent  string    `json:"xml_content,omitempty"` // 原始XML，用于调试
}

// SNSLocation 位置信息
type SNSLocation struct {
	City        string  `json:"city,omitempty"`
	Latitude    float64 `json:"latitude,omitempty"`
	Longitude   float64 `json:"longitude,omitempty"`
	POIName     string  `json:"poi_name,omitempty"`
	POIAddress  string  `json:"poi_address,omitempty"`
}

// SNSMedia 媒体信息
type SNSMedia struct {
	Type     string `json:"type"`     // image, video
	URL      string `json:"url,omitempty"`
	ThumbURL string `json:"thumb_url,omitempty"`
	Width    int    `json:"width,omitempty"`
	Height   int    `json:"height,omitempty"`
	Duration string `json:"duration,omitempty"`
}

// SNSArticle 文章信息
type SNSArticle struct {
	Title       string `json:"title"`
	Description string `json:"description"`
	URL         string `json:"url"`
	CoverURL    string `json:"cover_url"`
}

// SNSFinderFeed 视频号信息
type SNSFinderFeed struct {
	Nickname     string `json:"nickname"`
	Avatar       string `json:"avatar"`
	Desc         string `json:"desc"`
	MediaCount   int    `json:"media_count"`
	VideoURL     string `json:"video_url"`
	CoverURL     string `json:"cover_url"`
	ThumbURL     string `json:"thumb_url"`
	Width        int    `json:"width,omitempty"`
	Height       int    `json:"height,omitempty"`
	Duration     string `json:"duration,omitempty"`
}

// ParseSNSContent 解析朋友圈 XML 内容
func ParseSNSContent(xmlContent string) (*SNSPost, error) {
	post := &SNSPost{
		XMLContent: xmlContent,
	}

	// 提取 createTime
	createTime := extractXMLTag(xmlContent, "createTime")
	if createTime != "" {
		post.CreateTime, _ = strconv.ParseInt(createTime, 10, 64)
		post.CreateTimeStr = time.Unix(post.CreateTime, 0).Format("2006-01-02 15:04:05")
	}

	// 提取 username
	post.UserName = extractXMLTag(xmlContent, "username")

	// 提取 nickname
	post.NickName = extractXMLTag(xmlContent, "nickname")

	// 提取 contentDesc
	post.ContentDesc = extractXMLTag(xmlContent, "contentDesc")

	// 提取位置信息
	post.Location = parseSNSLocation(xmlContent)

	// 判断内容类型并提取相应信息
	contentType := extractXMLTag(xmlContent, "type")
	post.ContentType = parseSNSContentType(contentType)

	switch post.ContentType {
	case "image":
		post.MediaList = parseSNSImageMedia(xmlContent)
	case "video":
		post.MediaList = parseSNSVideoMedia(xmlContent)
	case "article":
		post.Article = parseSNSArticle(xmlContent)
	case "finder":
		post.FinderFeed = parseSNSFinderFeed(xmlContent)
	}

	return post, nil
}

// extractXMLTag 提取 XML 标签内容
func extractXMLTag(xml, tag string) string {
	re := regexp.MustCompile(`<` + tag + `>([^<]*)</` + tag + `>`)
	matches := re.FindStringSubmatch(xml)
	if len(matches) > 1 {
		return strings.TrimSpace(matches[1])
	}
	// 处理带属性的标签
	re = regexp.MustCompile(`<` + tag + `[^>]*>([^<]*)</` + tag + `>`)
	matches = re.FindStringSubmatch(xml)
	if len(matches) > 1 {
		return strings.TrimSpace(matches[1])
	}
	return ""
}

// extractXMLTagAttr 提取 XML 标签属性值
func extractXMLTagAttr(xml, tag, attr string) string {
	re := regexp.MustCompile(`<` + tag + `[^>]*` + attr + `="([^"]*)"`)
	matches := re.FindStringSubmatch(xml)
	if len(matches) > 1 {
		return matches[1]
	}
	return ""
}

// parseSNSContentType 解析内容类型
func parseSNSContentType(typeStr string) string {
	switch typeStr {
	case "1":
		return "image"
	case "6":
		return "video"
	case "3":
		return "article"
	case "15":
		return "video"
	case "28":
		return "finder"
	case "7":
		return "image"
	default:
		return "text"
	}
}

// parseSNSLocation 解析位置信息
func parseSNSLocation(xml string) *SNSLocation {
	loc := &SNSLocation{}

	city := extractXMLTagAttr(xml, "location", "city")
	if city == "" {
		city = extractXMLTag(xmlContentLocation(xml), "city")
	}
	loc.City = city

	lat := extractXMLTagAttr(xml, "location", "latitude")
	if lat != "" {
		loc.Latitude, _ = strconv.ParseFloat(lat, 64)
	}

	lon := extractXMLTagAttr(xml, "location", "longitude")
	if lon != "" {
		loc.Longitude, _ = strconv.ParseFloat(lon, 64)
	}

	loc.POIName = extractXMLTagAttr(xml, "location", "poiName")
	loc.POIAddress = extractXMLTagAttr(xml, "location", "poiAddress")

	if loc.City == "" && loc.POIName == "" {
		return nil
	}
	return loc
}

// xmlContentLocation 提取 location 标签内容
func xmlContentLocation(xml string) string {
	re := regexp.MustCompile(`<location[^>]*>([^<]*)</location>`)
	matches := re.FindStringSubmatch(xml)
	if len(matches) > 1 {
		return matches[1]
	}
	return ""
}

// parseSNSImageMedia 解析图片媒体
func parseSNSImageMedia(xml string) []SNSMedia {
	var mediaList []SNSMedia

	// 查找所有 media 标签
	re := regexp.MustCompile(`<media>(.*?)</media>`)
	matches := re.FindAllStringSubmatch(xml, -1)

	for _, match := range matches {
		if len(match) > 1 {
			media := SNSMedia{Type: "image"}
			mediaXML := match[1]

			// 提取 URL
			urlTag := extractXMLTag(mediaXML, "url")
			if urlTag == "" {
				urlTag = extractXMLTag(mediaXML, "thumb")
			}
			media.URL = html.UnescapeString(urlTag)

			// 提取尺寸
			width := extractXMLTagAttr(mediaXML, "size", "width")
			height := extractXMLTagAttr(mediaXML, "size", "height")
			if width != "" {
				media.Width, _ = strconv.Atoi(width)
			}
			if height != "" {
				media.Height, _ = strconv.Atoi(height)
			}

			mediaList = append(mediaList, media)
		}
	}

	return mediaList
}

// parseSNSVideoMedia 解析视频媒体
func parseSNSVideoMedia(xml string) []SNSMedia {
	var mediaList []SNSMedia

	// 查找所有 media 标签
	re := regexp.MustCompile(`<media>(.*?)</media>`)
	matches := re.FindAllStringSubmatch(xml, -1)

	for _, match := range matches {
		if len(match) > 1 {
			media := SNSMedia{Type: "video"}
			mediaXML := match[1]

			// 提取 URL
			media.URL = html.UnescapeString(extractXMLTag(mediaXML, "url"))
			media.ThumbURL = html.UnescapeString(extractXMLTag(mediaXML, "thumb"))

			// 提取尺寸
			width := extractXMLTagAttr(mediaXML, "size", "width")
			height := extractXMLTagAttr(mediaXML, "size", "height")
			if width != "" {
				media.Width, _ = strconv.Atoi(width)
			}
			if height != "" {
				media.Height, _ = strconv.Atoi(height)
			}

			// 提取时长
			duration := extractXMLTag(mediaXML, "videoDuration")
			if duration != "" {
				if d, err := strconv.ParseFloat(duration, 64); err == nil {
					media.Duration = fmt.Sprintf("%.2f秒", d)
				}
			}

			mediaList = append(mediaList, media)
		}
	}

	return mediaList
}

// parseSNSArticle 解析文章信息
func parseSNSArticle(xml string) *SNSArticle {
	article := &SNSArticle{}

	article.Title = extractXMLTag(xml, "title")
	article.Description = extractXMLTag(xml, "description")
	article.URL = html.UnescapeString(extractXMLTag(xml, "contentUrl"))

	// 提取封面图
	re := regexp.MustCompile(`<media>(.*?)</media>`)
	matches := re.FindStringSubmatch(xml)
	if len(matches) > 1 {
		mediaXML := matches[1]
		article.CoverURL = html.UnescapeString(extractXMLTag(mediaXML, "thumb"))
		if article.CoverURL == "" {
			article.CoverURL = html.UnescapeString(extractXMLTag(mediaXML, "url"))
		}
	}

	if article.Title == "" && article.URL == "" {
		return nil
	}

	return article
}

// parseSNSFinderFeed 解析视频号信息
func parseSNSFinderFeed(xml string) *SNSFinderFeed {
	feed := &SNSFinderFeed{}

	// 提取 finderFeed 标签内容
	re := regexp.MustCompile(`<finderFeed>(.*?)</finderFeed>`)
	matches := re.FindStringSubmatch(xml)
	if len(matches) <= 1 {
		return nil
	}

	feedXML := matches[1]

	feed.Nickname = extractXMLTag(feedXML, "nickname")
	feed.Avatar = html.UnescapeString(extractXMLTag(feedXML, "avatar"))
	feed.Desc = extractXMLTag(feedXML, "desc")

	// 提取媒体数量
	mediaCount := extractXMLTag(feedXML, "mediaCount")
	if mediaCount != "" {
		feed.MediaCount, _ = strconv.Atoi(mediaCount)
	}

	// 提取视频信息
	mediaRe := regexp.MustCompile(`<media>(.*?)</media>`)
	mediaMatches := mediaRe.FindStringSubmatch(feedXML)
	if len(mediaMatches) > 1 {
		mediaXML := mediaMatches[1]
		feed.VideoURL = html.UnescapeString(extractXMLTag(mediaXML, "url"))
		feed.ThumbURL = html.UnescapeString(extractXMLTag(mediaXML, "thumbUrl"))
		feed.CoverURL = html.UnescapeString(extractXMLTag(mediaXML, "coverUrl"))

		// 提取尺寸
		width := extractXMLTagAttr(mediaXML, "size", "width")
		height := extractXMLTagAttr(mediaXML, "size", "height")
		if width != "" {
			if w, err := strconv.Atoi(width); err == nil {
				feed.Width = w
			}
		}
		if height != "" {
			if h, err := strconv.Atoi(height); err == nil {
				feed.Height = h
			}
		}

		// 提取时长
		duration := extractXMLTag(mediaXML, "videoPlayDuration")
		if duration != "" {
			if d, err := strconv.ParseInt(duration, 10, 64); err == nil {
				feed.Duration = fmt.Sprintf("%d秒", d/10)
			}
		}
	}

	if feed.Nickname == "" {
		return nil
	}

	return feed
}

// FormatAsText 格式化为纯文本
func (p *SNSPost) FormatAsText() string {
	var sb strings.Builder

	sb.WriteString(fmt.Sprintf("📅 %s\n", p.CreateTimeStr))
	if p.NickName != "" {
		sb.WriteString(fmt.Sprintf("👤 %s\n", p.NickName))
	}

	if p.ContentDesc != "" {
		sb.WriteString(fmt.Sprintf("💬 %s\n", p.ContentDesc))
	}

	if p.Location != nil {
		sb.WriteString("📍 ")
		if p.Location.POIName != "" {
			sb.WriteString(p.Location.POIName)
			if p.Location.POIAddress != "" {
				sb.WriteString(fmt.Sprintf(" (%s)", p.Location.POIAddress))
			}
		} else if p.Location.City != "" {
			sb.WriteString(p.Location.City)
		}
		sb.WriteString("\n")
	}

	switch p.ContentType {
	case "image":
		sb.WriteString(fmt.Sprintf("🖼️ 图片 (%d张)\n", len(p.MediaList)))
	case "video":
		if len(p.MediaList) > 0 && p.MediaList[0].Duration != "" {
			sb.WriteString(fmt.Sprintf("🎬 视频 (%s)\n", p.MediaList[0].Duration))
		} else {
			sb.WriteString("🎬 视频\n")
		}
	case "article":
		if p.Article != nil {
			sb.WriteString(fmt.Sprintf("📰 文章: %s\n", p.Article.Title))
			sb.WriteString(fmt.Sprintf("   %s\n", p.Article.URL))
		}
	case "finder":
		if p.FinderFeed != nil {
			sb.WriteString(fmt.Sprintf("📺 视频号: %s\n", p.FinderFeed.Nickname))
			if p.FinderFeed.Desc != "" {
				sb.WriteString(fmt.Sprintf("   %s\n", p.FinderFeed.Desc))
			}
		}
	}

	return sb.String()
}

// ToJSON 转换为 JSON
func (p *SNSPost) ToJSON() (string, error) {
	bytes, err := json.MarshalIndent(p, "", "  ")
	if err != nil {
		return "", err
	}
	return string(bytes), nil
}
