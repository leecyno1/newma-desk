from __future__ import annotations

import requests
from typing import Any, Dict, List, Optional

from .wechat_gateway import load_config
from ..db import SessionLocal


class WechatApiClient:
    """Complete wechatapi.net iPad protocol client.

    Base URL: http://api.wechatapi.net/finder/v2/api
    Auth: VideosApi-token header + appId in body
    Reference: https://post.wechatapi.net/doc-8561747
    """

    def __init__(
        self,
        *,
        base_url: str | None = None,
        token: str | None = None,
        header_name: str | None = None,
        app_id: str | None = None,
    ):
        conf = {}
        if base_url is None or token is None or header_name is None or app_id is None:
            db = SessionLocal()
            try:
                conf = load_config(db)
            finally:
                db.close()
        self.base_url = str(base_url or conf.get("base_url") or "").strip().rstrip("/")
        self.token = str(token or conf.get("token") or "").strip()
        self.header_name = str(header_name or conf.get("header_name") or "VideosApi-token").strip() or "VideosApi-token"
        self.app_id = str(app_id or conf.get("app_id") or "").strip()
        try:
            self._session = requests.Session()
            self._session.trust_env = False
        except Exception:
            self._session = None

    # ── core ──

    def configured(self) -> bool:
        return bool(self.base_url and self.token and self.app_id)

    def _headers(self) -> dict[str, str]:
        if not self.token:
            return {}
        return {self.header_name: self.token}

    def _post(self, path: str, payload: dict[str, Any], *, timeout: float = 15) -> Dict[str, Any]:
        if not self.configured():
            raise RuntimeError("wechatapi gateway not configured")
        url = f"{self.base_url}{path if path.startswith('/') else '/' + path}"
        if self._session is not None:
            resp = self._session.post(url, json=payload, headers=self._headers(), timeout=timeout)
        else:
            resp = requests.post(
                url,
                json=payload,
                headers=self._headers(),
                timeout=timeout,
                proxies={"http": None, "https": None},
            )
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict) and str(data.get("ret")) == "200":
            return data
        raise RuntimeError(str(data.get("msg") if isinstance(data, dict) else data))

    # ═══════════════════════════════════════════════════════════════
    #  Login Module
    # ═══════════════════════════════════════════════════════════════

    def get_login_qrcode(
        self,
        *,
        region_id: str = "11000",
        device_type: str = "ipad",
        app_id: str = "",
        proxy_ip: str = "",
        ttuid: str = "",
    ) -> Dict[str, Any]:
        """Get WeChat login QR code. First login: pass app_id="". Subsequent: pass known app_id.

        Returns: {qrData, qrUrl, qrImgBase64, uuid, appId}
        """
        return self._post(
            "/login/getLoginQrCode",
            {
                "appId": str(app_id or "").strip(),
                "proxyIp": str(proxy_ip or "").strip(),
                "regionId": str(region_id or "11000").strip(),
                "type": str(device_type or "ipad").strip(),
                "ttuid": str(ttuid or "").strip(),
            },
        )

    def check_login(
        self,
        *,
        uuid: str,
        app_id: str = "",
        proxy_ip: str = "",
        captch_code: str = "",
        auto_sliding: bool = True,
    ) -> Dict[str, Any]:
        """Poll login status after scanning QR code. Call every 5s.

        Returns: {uuid, headImgUrl, nickName, status, loginInfo: {wxid, nickName, mobile, alias}}
        Status: 0=not scanned, 1=scanned not confirmed, 2=success, 4=cancelled
        """
        return self._post(
            "/login/checkLogin",
            {
                "appId": str(app_id or self.app_id).strip(),
                "proxyIp": str(proxy_ip or "").strip(),
                "uuid": str(uuid or "").strip(),
                "captchCode": str(captch_code or "").strip(),
                "autoSliding": bool(auto_sliding),
            },
        )

    def check_online(self) -> Dict[str, Any]:
        return self._post("/login/checkOnline", {"appId": self.app_id})

    def dialog_login(self, *, app_id: str = "") -> Dict[str, Any]:
        """Dialog login (alternative login method)."""
        return self._post("/login/dialogLogin", {"appId": str(app_id or self.app_id).strip()})

    def logout(self) -> Dict[str, Any]:
        return self._post("/login/logout", {"appId": self.app_id})

    def reconnection(self) -> Dict[str, Any]:
        """Reconnect after abnormal disconnection."""
        return self._post("/login/reconnection", {"appId": self.app_id})

    def set_proxy(self, *, proxy_ip: str) -> Dict[str, Any]:
        """Set proxy for the device."""
        return self._post(
            "/login/setProxy",
            {"appId": self.app_id, "proxyIp": str(proxy_ip or "").strip()},
        )

    def set_callback(self, callback_url: str) -> Dict[str, Any]:
        return self._post(
            "/login/setCallback",
            {"appId": self.app_id, "callbackUrl": str(callback_url or "").strip(), "token": self.token},
        )

    # ═══════════════════════════════════════════════════════════════
    #  Contact Module
    # ═══════════════════════════════════════════════════════════════

    def fetch_contacts_list(self) -> Dict[str, Any]:
        """Get full contacts list (friends + saved chatrooms + followed official accounts).

        Long-running call; use fetch_contacts_list_cache for cached results.
        Returns: {friends: [wxid, ...], chatrooms: [id, ...], ghs: [id, ...]}
        """
        return self._post("/contacts/fetchContactsList", {"appId": self.app_id}, timeout=180)

    def fetch_contacts_list_cache(self) -> Dict[str, Any]:
        """Get cached contacts list (10-min cache)."""
        return self._post("/contacts/fetchContactsListCache", {"appId": self.app_id}, timeout=30)

    def search_contact(self, *, contacts_info: str) -> Dict[str, Any]:
        """Search for a contact by wechat ID / phone number / etc.

        Returns: {v3, nickName, sex, bigHeadImgUrl, smallHeadImgUrl, v4}
        v3/v4 can be used for add_contact().
        """
        return self._post(
            "/contacts/search",
            {"appId": self.app_id, "contactsInfo": str(contacts_info or "").strip()},
        )

    def add_contact(
        self,
        *,
        scene: int,
        option: int,
        v3: str,
        v4: str,
        content: str = "",
    ) -> Dict[str, Any]:
        """Add/accept/reject friend request.

        scene: 3=wechat_id, 4=QQ, 8=from_group, 15=phone
        option: 2=add, 3=accept, 4=reject
        """
        return self._post(
            "/contacts/addContacts",
            {
                "appId": self.app_id,
                "scene": int(scene),
                "option": int(option),
                "v3": str(v3 or "").strip(),
                "v4": str(v4 or "").strip(),
                "content": str(content or "").strip(),
            },
        )

    def delete_friend(self, *, wxid: str) -> Dict[str, Any]:
        return self._post(
            "/contacts/deleteFriend",
            {"appId": self.app_id, "wxid": str(wxid or "").strip()},
        )

    def get_brief_info(self, *, wxids: List[str]) -> Dict[str, Any]:
        """Get brief info for contacts/groups. wxids: list of wechat IDs."""
        return self._post(
            "/contacts/getBriefInfo",
            {"appId": self.app_id, "wxids": [str(w or "").strip() for w in (wxids or [])]},
            timeout=45,
        )

    def get_detail_info(self, *, wxids: List[str]) -> Dict[str, Any]:
        """Get detailed info for contacts/groups."""
        return self._post(
            "/contacts/getDetailInfo",
            {"appId": self.app_id, "wxids": [str(w or "").strip() for w in (wxids or [])]},
        )

    def set_friend_remark(self, *, wxid: str, remark: str) -> Dict[str, Any]:
        return self._post(
            "/contacts/setFriendRemark",
            {"appId": self.app_id, "wxid": str(wxid or "").strip(), "remark": str(remark or "").strip()},
        )

    def set_friend_permissions(self, *, wxid: str, only_chat: bool = True) -> Dict[str, Any]:
        """Set friend to 'chat only' mode."""
        return self._post(
            "/contacts/setFriendPermissions",
            {"appId": self.app_id, "wxid": str(wxid or "").strip(), "onlyChat": bool(only_chat)},
        )

    def check_relation(self, *, wxids: List[str]) -> Dict[str, Any]:
        """Check friendship status for given wxids."""
        return self._post(
            "/contacts/checkRelation",
            {"appId": self.app_id, "wxids": [str(w or "").strip() for w in (wxids or [])]},
        )

    def get_phone_address_list(self) -> Dict[str, Any]:
        return self._post("/contacts/getPhoneAddressList", {"appId": self.app_id})

    def upload_phone_address_list(self, *, phones: List[str]) -> Dict[str, Any]:
        return self._post(
            "/contacts/uploadPhoneAddressList",
            {"appId": self.app_id, "phones": [str(p or "").strip() for p in (phones or [])]},
        )

    # ═══════════════════════════════════════════════════════════════
    #  Message Module — Send
    # ═══════════════════════════════════════════════════════════════

    def send_text(self, to_wxid: str, text: str) -> Dict[str, Any]:
        return self._post(
            "/message/postText",
            {
                "appId": self.app_id,
                "toWxid": str(to_wxid or "").strip(),
                "content": str(text or ""),
            },
        )

    def send_image(self, to_wxid: str, image_url: str) -> Dict[str, Any]:
        return self._post(
            "/message/postImage",
            {
                "appId": self.app_id,
                "toWxid": str(to_wxid or "").strip(),
                "imgUrl": str(image_url or "").strip(),
            },
        )

    def send_file(self, to_wxid: str, file_url: str, file_name: str = "") -> Dict[str, Any]:
        return self._post(
            "/message/postFile",
            {
                "appId": self.app_id,
                "toWxid": str(to_wxid or "").strip(),
                "fileUrl": str(file_url or "").strip(),
                "fileName": str(file_name or "").strip(),
            },
        )

    def send_link(
        self, to_wxid: str, url: str, title: str = "", desc: str = "", thumb_url: str = ""
    ) -> Dict[str, Any]:
        return self._post(
            "/message/postLink",
            {
                "appId": self.app_id,
                "toWxid": str(to_wxid or "").strip(),
                "linkUrl": str(url or "").strip(),
                "title": str(title or url or "链接").strip(),
                "desc": str(desc or "").strip(),
                "thumbUrl": str(thumb_url or "").strip(),
            },
        )

    def send_voice(self, to_wxid: str, voice_url: str, voice_duration: int) -> Dict[str, Any]:
        """Send voice message (silk format). voice_duration in milliseconds."""
        return self._post(
            "/message/postVoice",
            {
                "appId": self.app_id,
                "toWxid": str(to_wxid or "").strip(),
                "voiceUrl": str(voice_url or "").strip(),
                "voiceDuration": int(voice_duration or 0),
            },
        )

    def send_video(
        self, to_wxid: str, video_url: str, thumb_url: str, video_duration: int
    ) -> Dict[str, Any]:
        """Send video message. video_duration in seconds.

        Returns cdn info (aesKey, fileId, length) usable for forward_video().
        """
        return self._post(
            "/message/postVideo",
            {
                "appId": self.app_id,
                "toWxid": str(to_wxid or "").strip(),
                "videoUrl": str(video_url or "").strip(),
                "thumbUrl": str(thumb_url or "").strip(),
                "videoDuration": int(video_duration or 0),
            },
        )

    def send_namecard(self, to_wxid: str, nick_name: str, name_card_wxid: str) -> Dict[str, Any]:
        """Send a contact card."""
        return self._post(
            "/message/postNameCard",
            {
                "appId": self.app_id,
                "toWxid": str(to_wxid or "").strip(),
                "nickName": str(nick_name or "").strip(),
                "nameCardWxid": str(name_card_wxid or "").strip(),
            },
        )

    def send_location(self, to_wxid: str, content_xml: str) -> Dict[str, Any]:
        """Send a location message. content_xml is the location XML from callback."""
        return self._post(
            "/message/postLocation",
            {
                "appId": self.app_id,
                "toWxid": str(to_wxid or "").strip(),
                "content": str(content_xml or "").strip(),
            },
        )

    def send_emoji(self, to_wxid: str, emoji_md5: str, emoji_size: int) -> Dict[str, Any]:
        return self._post(
            "/message/postEmoji",
            {
                "appId": self.app_id,
                "toWxid": str(to_wxid or "").strip(),
                "emojiMd5": str(emoji_md5 or "").strip(),
                "emojiSize": int(emoji_size or 0),
            },
        )

    def send_miniapp(
        self,
        to_wxid: str,
        *,
        mini_app_id: str,
        display_name: str,
        page_path: str,
        cover_img_url: str,
        title: str,
        user_name: str,
    ) -> Dict[str, Any]:
        """Send a mini-program card."""
        return self._post(
            "/message/postMiniApp",
            {
                "appId": self.app_id,
                "toWxid": str(to_wxid or "").strip(),
                "miniAppId": str(mini_app_id or "").strip(),
                "displayName": str(display_name or "").strip(),
                "pagePath": str(page_path or "").strip(),
                "coverImgUrl": str(cover_img_url or "").strip(),
                "title": str(title or "").strip(),
                "userName": str(user_name or "").strip(),
            },
        )

    def send_appmsg(self, to_wxid: str, appmsg_xml: str) -> Dict[str, Any]:
        """Send a generic appmsg (article share, music, quote reply, etc).

        Pass the appmsg XML node from a callback message, modified as needed.
        """
        return self._post(
            "/message/postAppMsg",
            {
                "appId": self.app_id,
                "toWxid": str(to_wxid or "").strip(),
                "appmsg": str(appmsg_xml or "").strip(),
            },
        )

    def send_finder_msg(self, to_wxid: str, xml: str) -> Dict[str, Any]:
        """Send a 视频号 (finder) message."""
        return self._post(
            "/message/sendFinderMsg",
            {
                "appId": self.app_id,
                "toWxid": str(to_wxid or "").strip(),
                "xml": str(xml or "").strip(),
            },
        )

    # ── Forward ──

    def forward_image(self, to_wxid: str, xml: str) -> Dict[str, Any]:
        """Forward an image using cdn info from callback or send_image response."""
        return self._post(
            "/message/forwardImage",
            {"appId": self.app_id, "toWxid": str(to_wxid or "").strip(), "xml": str(xml or "").strip()},
        )

    def forward_video(self, to_wxid: str, xml: str) -> Dict[str, Any]:
        return self._post(
            "/message/forwardVideo",
            {"appId": self.app_id, "toWxid": str(to_wxid or "").strip(), "xml": str(xml or "").strip()},
        )

    def forward_file(self, to_wxid: str, xml: str) -> Dict[str, Any]:
        return self._post(
            "/message/forwardFile",
            {"appId": self.app_id, "toWxid": str(to_wxid or "").strip(), "xml": str(xml or "").strip()},
        )

    def forward_url(self, to_wxid: str, xml: str) -> Dict[str, Any]:
        return self._post(
            "/message/forwardUrl",
            {"appId": self.app_id, "toWxid": str(to_wxid or "").strip(), "xml": str(xml or "").strip()},
        )

    def forward_miniapp(self, to_wxid: str, xml: str) -> Dict[str, Any]:
        return self._post(
            "/message/forwardMiniApp",
            {"appId": self.app_id, "toWxid": str(to_wxid or "").strip(), "xml": str(xml or "").strip()},
        )

    # ── Download ──

    def download_image(self, *, aeskey: str, file_id: str, img_type: str = "mid") -> Dict[str, Any]:
        """Download an image. img_type: 'mid' | 'thumb' | 'hd'."""
        return self._post(
            "/message/downloadImage",
            {"appId": self.app_id, "aeskey": str(aeskey), "fileId": str(file_id), "type": str(img_type)},
        )

    def download_image_by_xml(self, *, xml: str, img_type: int = 2) -> Dict[str, Any]:
        """Get a temporary URL for an image callback XML.

        img_type: 1=HD, 2=regular, 3=thumbnail.
        """
        return self._post(
            "/message/downloadImage",
            {"appId": self.app_id, "xml": str(xml or ""), "type": int(img_type or 2)},
        )

    def download_video(self, *, aeskey: str, file_id: str) -> Dict[str, Any]:
        return self._post(
            "/message/downloadVideo",
            {"appId": self.app_id, "aeskey": str(aeskey), "fileId": str(file_id)},
        )

    def download_file(self, *, aeskey: str, file_id: str) -> Dict[str, Any]:
        return self._post(
            "/message/downloadFile",
            {"appId": self.app_id, "aeskey": str(aeskey), "fileId": str(file_id)},
        )

    def download_file_by_xml(self, *, xml: str) -> Dict[str, Any]:
        """Get a temporary download URL for a file message XML callback."""
        return self._post(
            "/message/downloadFile",
            {"appId": self.app_id, "xml": str(xml or "")},
        )

    def download_voice(self, *, aeskey: str, file_id: str) -> Dict[str, Any]:
        return self._post(
            "/message/downloadVoice",
            {"appId": self.app_id, "aeskey": str(aeskey), "fileId": str(file_id)},
        )

    def download_emoji(self, *, emoji_md5: str) -> Dict[str, Any]:
        return self._post(
            "/message/downloadEmojiMd5",
            {"appId": self.app_id, "emojiMd5": str(emoji_md5)},
        )

    def cdn_download(self, *, aeskey: str, file_id: str, file_type: str = "image") -> Dict[str, Any]:
        """Generic CDN download."""
        return self._post(
            "/message/downloadCdn",
            {"appId": self.app_id, "aesKey": str(aeskey), "fileId": str(file_id), "type": str(file_type), "totalSize": "0", "suffix": ""},
        )

    def download_cdn_file(self, *, aeskey: str, file_id: str, total_size: str = "0", suffix: str = "") -> Dict[str, Any]:
        return self._post(
            "/message/downloadCdn",
            {
                "appId": self.app_id,
                "aesKey": str(aeskey or ""),
                "fileId": str(file_id or ""),
                "type": "5",
                "totalSize": str(total_size or "0"),
                "suffix": str(suffix or "").lstrip("."),
            },
        )

    # ── Revoke ──

    def revoke_message(self, to_wxid: str, msg_id: str, new_msg_id: str, create_time: str) -> Dict[str, Any]:
        """Revoke a sent message. All IDs must be from the original send response."""
        return self._post(
            "/message/revokeMsg",
            {
                "appId": self.app_id,
                "toWxid": str(to_wxid or "").strip(),
                "msgId": str(msg_id or "").strip(),
                "newMsgId": str(new_msg_id or "").strip(),
                "createTime": str(create_time or "").strip(),
            },
        )

    # ═══════════════════════════════════════════════════════════════
    #  Group Module
    # ═══════════════════════════════════════════════════════════════

    def create_chatroom(self, *, wxids: List[str]) -> Dict[str, Any]:
        """Create a group chat. Minimum 2 friends required."""
        return self._post(
            "/group/createChatroom",
            {"appId": self.app_id, "wxids": [str(w or "").strip() for w in (wxids or [])]},
        )

    def modify_chatroom_name(self, *, chatroom_id: str, name: str) -> Dict[str, Any]:
        return self._post(
            "/group/modifyChatroomName",
            {"appId": self.app_id, "chatroomId": str(chatroom_id or "").strip(), "name": str(name or "").strip()},
        )

    def modify_chatroom_remark(self, *, chatroom_id: str, remark: str) -> Dict[str, Any]:
        """Set group remark (visible only to self)."""
        return self._post(
            "/group/modifyChatroomRemark",
            {"appId": self.app_id, "chatroomId": str(chatroom_id or "").strip(), "remark": str(remark or "").strip()},
        )

    def modify_chatroom_nickname_for_self(self, *, chatroom_id: str, nick_name: str) -> Dict[str, Any]:
        """Set my display name in a group."""
        return self._post(
            "/group/modifyChatroomNickNameForSelf",
            {"appId": self.app_id, "chatroomId": str(chatroom_id or "").strip(), "nickName": str(nick_name or "").strip()},
        )

    def invite_member(self, *, chatroom_id: str, wxids: List[str]) -> Dict[str, Any]:
        return self._post(
            "/group/inviteMember",
            {"appId": self.app_id, "chatroomId": str(chatroom_id or "").strip(), "wxids": [str(w or "").strip() for w in (wxids or [])]},
        )

    def remove_member(self, *, chatroom_id: str, wxid: str) -> Dict[str, Any]:
        return self._post(
            "/group/removeMember",
            {"appId": self.app_id, "chatroomId": str(chatroom_id or "").strip(), "wxid": str(wxid or "").strip()},
        )

    def quit_chatroom(self, *, chatroom_id: str) -> Dict[str, Any]:
        return self._post("/group/quitChatroom", {"appId": self.app_id, "chatroomId": str(chatroom_id or "").strip()})

    def get_chatroom_info(self, *, chatroom_id: str) -> Dict[str, Any]:
        return self._post("/group/getChatroomInfo", {"appId": self.app_id, "chatroomId": str(chatroom_id or "").strip()})

    def get_chatroom_member_list(self, *, chatroom_id: str) -> Dict[str, Any]:
        return self._post("/group/getChatroomMemberList", {"appId": self.app_id, "chatroomId": str(chatroom_id or "").strip()})

    def get_chatroom_member_detail(self, *, chatroom_id: str, member_wxids: List[str]) -> Dict[str, Any]:
        return self._post(
            "/group/getChatroomMemberDetail",
            {"appId": self.app_id, "chatroomId": str(chatroom_id or "").strip(), "memberWxids": [str(m or "").strip() for m in (member_wxids or [])]},
        )

    def set_chatroom_announcement(self, *, chatroom_id: str, announcement: str) -> Dict[str, Any]:
        """Owner/admin only."""
        return self._post(
            "/group/setChatroomAnnouncement",
            {"appId": self.app_id, "chatroomId": str(chatroom_id or "").strip(), "announcement": str(announcement or "").strip()},
        )

    def get_chatroom_announcement(self, *, chatroom_id: str) -> Dict[str, Any]:
        return self._post("/group/getChatroomAnnouncement", {"appId": self.app_id, "chatroomId": str(chatroom_id or "").strip()})

    def agree_join_room(self, *, chatroom_id: str, url: str) -> Dict[str, Any]:
        return self._post(
            "/group/agreeJoinRoom",
            {"appId": self.app_id, "chatroomId": str(chatroom_id or "").strip(), "url": str(url or "").strip()},
        )

    def add_group_member_as_friend(self, *, chatroom_id: str, member_wxid: str) -> Dict[str, Any]:
        return self._post(
            "/group/addGroupMemberAsFriend",
            {"appId": self.app_id, "chatroomId": str(chatroom_id or "").strip(), "memberWxid": str(member_wxid or "").strip()},
        )

    def get_chatroom_qrcode(self, *, chatroom_id: str) -> Dict[str, Any]:
        return self._post("/group/getChatroomQrCode", {"appId": self.app_id, "chatroomId": str(chatroom_id or "").strip()})

    def save_to_contact_list(self, *, chatroom_id: str) -> Dict[str, Any]:
        """Save group to contacts list."""
        return self._post("/group/saveContractList", {"appId": self.app_id, "chatroomId": str(chatroom_id or "").strip()})

    def admin_operate(self, *, chatroom_id: str, wxid: str, op_type: int) -> Dict[str, Any]:
        """op_type: 1=add admin, 2=remove admin, 3=transfer ownership."""
        return self._post(
            "/group/adminOperate",
            {"appId": self.app_id, "chatroomId": str(chatroom_id or "").strip(), "wxid": str(wxid or "").strip(), "type": int(op_type)},
        )

    def pin_chat(self, *, chatroom_id: str, pin: bool = True) -> Dict[str, Any]:
        return self._post("/group/pinChat", {"appId": self.app_id, "chatroomId": str(chatroom_id or "").strip(), "pin": bool(pin)})

    def set_msg_silence(self, *, chatroom_id: str, silence: bool = True) -> Dict[str, Any]:
        return self._post(
            "/group/setMsgSilence",
            {"appId": self.app_id, "chatroomId": str(chatroom_id or "").strip(), "silence": bool(silence)},
        )

    def join_room_using_qrcode(self, *, qr_url: str) -> Dict[str, Any]:
        return self._post("/group/joinRoomUsingQrCode", {"appId": self.app_id, "qrUrl": str(qr_url or "").strip()})

    def room_access_apply_check_approve(self, *, chatroom_id: str, url: str, approve: bool = True) -> Dict[str, Any]:
        return self._post(
            "/group/roomAccessApplyCheckApprove",
            {"appId": self.app_id, "chatroomId": str(chatroom_id or "").strip(), "url": str(url or "").strip(), "approve": bool(approve)},
        )

    # ═══════════════════════════════════════════════════════════════
    #  Moments (朋友圈) Module
    # ═══════════════════════════════════════════════════════════════

    def sns_list(self, *, max_id: int = 0, first_page_md5: str = "", decrypt: bool = True) -> Dict[str, Any]:
        """Get own moments timeline. Paginated."""
        return self._post(
            "/sns/snsList",
            {
                "appId": self.app_id,
                "maxId": max_id,
                "firstPageMd5": str(first_page_md5 or "").strip(),
                "decrypt": bool(decrypt),
            },
        )

    def contact_sns_list(self, *, wxid: str, max_id: int = 0, first_page_md5: str = "") -> Dict[str, Any]:
        """Get a contact's moments timeline."""
        return self._post(
            "/sns/contactsSnsList",
            {
                "appId": self.app_id,
                "wxid": str(wxid or "").strip(),
                "maxId": max_id,
                "firstPageMd5": str(first_page_md5 or "").strip(),
            },
        )

    def sns_details(self, *, sns_id: int) -> Dict[str, Any]:
        return self._post("/sns/snsDetails", {"appId": self.app_id, "snsId": int(sns_id)})

    def send_text_sns(self, *, content: str) -> Dict[str, Any]:
        """Post a text-only moment. Note: new device login blocks moments for 1-3 days."""
        return self._post(
            "/sns/sendTextSns",
            {"appId": self.app_id, "content": str(content or "").strip()},
        )

    def send_image_sns(self, *, image_ids: List[str], description: str = "") -> Dict[str, Any]:
        """Post an image moment. Use upload_sns_image() first, then pass returned IDs."""
        return self._post(
            "/sns/sendImgSns",
            {
                "appId": self.app_id,
                "imageIds": [str(i or "").strip() for i in (image_ids or [])],
                "description": str(description or "").strip(),
            },
        )

    def send_video_sns(self, *, video_id: str, description: str = "", preview_id: str = "") -> Dict[str, Any]:
        return self._post(
            "/sns/sendVideoSns",
            {
                "appId": self.app_id,
                "videoId": str(video_id or "").strip(),
                "description": str(description or "").strip(),
                "previewId": str(preview_id or "").strip(),
            },
        )

    def send_url_sns(self, *, url: str, title: str = "", description: str = "") -> Dict[str, Any]:
        return self._post(
            "/sns/sendUrlSns",
            {
                "appId": self.app_id,
                "url": str(url or "").strip(),
                "title": str(title or "").strip(),
                "description": str(description or "").strip(),
            },
        )

    def send_finder_sns(self, *, finder_xml: str) -> Dict[str, Any]:
        """Share a 视频号 to moments."""
        return self._post(
            "/sns/sendFinderSns",
            {"appId": self.app_id, "finderXml": str(finder_xml or "").strip()},
        )

    def forward_sns(self, *, sns_id: int, wxid: str, description: str = "") -> Dict[str, Any]:
        """Forward/retweet a moment."""
        return self._post(
            "/sns/forwardSns",
            {
                "appId": self.app_id,
                "snsId": int(sns_id),
                "wxid": str(wxid or "").strip(),
                "description": str(description or "").strip(),
            },
        )

    def like_sns(self, *, sns_id: int, wxid: str, oper_type: int = 1) -> Dict[str, Any]:
        """Like/unlike a moment. oper_type: 1=like, 2=unlike. wxid is the moment AUTHOR's ID."""
        return self._post(
            "/sns/likeSns",
            {"appId": self.app_id, "snsId": int(sns_id), "wxid": str(wxid or "").strip(), "operType": int(oper_type)},
        )

    def comment_sns(
        self, *, sns_id: int, wxid: str, content: str, oper_type: int = 1, reply_to: str = ""
    ) -> Dict[str, Any]:
        """Comment on a moment. oper_type: 1=comment, 2=delete comment. wxid is author's ID."""
        payload: Dict[str, Any] = {
            "appId": self.app_id,
            "snsId": int(sns_id),
            "wxid": str(wxid or "").strip(),
            "content": str(content or "").strip(),
            "operType": int(oper_type),
        }
        if reply_to:
            payload["replyTo"] = str(reply_to).strip()
        return self._post("/sns/commentSns", payload)

    def delete_sns(self, *, sns_id: int) -> Dict[str, Any]:
        return self._post("/sns/delSns", {"appId": self.app_id, "snsId": int(sns_id)})

    def upload_sns_image(self, *, image_url: str) -> Dict[str, Any]:
        """Upload an image for moments posting. Returns image ID to use in send_image_sns()."""
        return self._post(
            "/sns/uploadSnsImage",
            {"appId": self.app_id, "imageUrl": str(image_url or "").strip()},
        )

    def upload_sns_video(self, *, video_url: str, thumb_url: str = "") -> Dict[str, Any]:
        return self._post(
            "/sns/uploadSnsVideo",
            {"appId": self.app_id, "videoUrl": str(video_url or "").strip(), "thumbUrl": str(thumb_url or "").strip()},
        )

    def download_sns_video(self, *, sns_id: int, url: str) -> Dict[str, Any]:
        return self._post(
            "/sns/downloadSnsVideo",
            {"appId": self.app_id, "snsId": int(sns_id), "url": str(url or "").strip()},
        )

    def sns_set_privacy(self, *, sns_id: int, privacy: bool = True) -> Dict[str, Any]:
        """Set a moment to private/public."""
        return self._post(
            "/sns/snsSetPrivacy",
            {"appId": self.app_id, "snsId": int(sns_id), "privacy": bool(privacy)},
        )

    def sns_visible_scope(self, *, sns_id: int, option: int = 0) -> Dict[str, Any]:
        """Set moment visibility scope. option: refer to API docs."""
        return self._post(
            "/sns/snsVisibleScope",
            {"appId": self.app_id, "snsId": int(sns_id), "option": int(option)},
        )

    def stranger_visibility_enabled(self, *, enabled: bool = True) -> Dict[str, Any]:
        return self._post(
            "/sns/strangerVisibilityEnabled",
            {"appId": self.app_id, "enabled": bool(enabled)},
        )

    # ═══════════════════════════════════════════════════════════════
    #  Label Module
    # ═══════════════════════════════════════════════════════════════

    def add_label(self, *, name: str) -> Dict[str, Any]:
        return self._post("/label/add", {"appId": self.app_id, "name": str(name or "").strip()})

    def delete_label(self, *, label_id: str) -> Dict[str, Any]:
        return self._post("/label/delete", {"appId": self.app_id, "labelId": str(label_id or "").strip()})

    def list_labels(self) -> Dict[str, Any]:
        return self._post("/label/list", {"appId": self.app_id})

    def modify_member_labels(self, *, label_ids: List[str], wxids: List[str]) -> Dict[str, Any]:
        """Assign labels to contacts."""
        return self._post(
            "/label/modifyMemberList",
            {
                "appId": self.app_id,
                "labelIds": [str(l or "").strip() for l in (label_ids or [])],
                "wxids": [str(w or "").strip() for w in (wxids or [])],
            },
        )

    # ═══════════════════════════════════════════════════════════════
    #  Favorite Module
    # ═══════════════════════════════════════════════════════════════

    def sync_favorites(self) -> Dict[str, Any]:
        """Sync favorites from device. Returns the sync key needed for get_favorite_content()."""
        return self._post("/favor/sync", {"appId": self.app_id})

    def get_favorite_content(self, *, fav_id: int) -> Dict[str, Any]:
        return self._post("/favor/getContent", {"appId": self.app_id, "favId": int(fav_id)})

    def delete_favorite(self, *, fav_id: int) -> Dict[str, Any]:
        return self._post("/favor/delete", {"appId": self.app_id, "favId": int(fav_id)})

    # ═══════════════════════════════════════════════════════════════
    #  Personal Module
    # ═══════════════════════════════════════════════════════════════

    def get_profile(self) -> Dict[str, Any]:
        return self._post("/personal/getProfile", {"appId": self.app_id})

    def get_qrcode(self) -> Dict[str, Any]:
        """Get own WeChat QR code."""
        return self._post("/personal/getQrCode", {"appId": self.app_id})

    def get_safety_info(self) -> Dict[str, Any]:
        """Get device records."""
        return self._post("/personal/getSafetyInfo", {"appId": self.app_id})

    def privacy_settings(self, *, option: int) -> Dict[str, Any]:
        return self._post("/personal/privacySettings", {"appId": self.app_id, "option": int(option)})

    def update_profile(self, *, field_name: str, field_value: str) -> Dict[str, Any]:
        """Update profile fields one at a time. E.g. nickName, signature, sex."""
        return self._post(
            "/personal/updateProfile",
            {"appId": self.app_id, str(field_name or "").strip(): str(field_value or "").strip()},
        )

    def update_head_image(self, *, head_img_url: str) -> Dict[str, Any]:
        return self._post(
            "/personal/updateHeadImg",
            {"appId": self.app_id, "headImgUrl": str(head_img_url or "").strip()},
        )

    # ═══════════════════════════════════════════════════════════════
    #  Finder (视频号) Module
    # ═══════════════════════════════════════════════════════════════

    def finder_search(self, *, keyword: str) -> Dict[str, Any]:
        return self._post("/finder/search", {"appId": self.app_id, "keyword": str(keyword or "").strip()})

    def finder_get_profile(self, *, finder_username: str = "") -> Dict[str, Any]:
        return self._post("/finder/getProfile", {"appId": self.app_id, "finderUsername": str(finder_username or "").strip()})

    def finder_create(self, *, name: str, description: str = "") -> Dict[str, Any]:
        return self._post(
            "/finder/createFinder",
            {"appId": self.app_id, "name": str(name or "").strip(), "description": str(description or "").strip()},
        )

    def finder_post_private_letter(self, *, msgsessionid: str, content: str) -> Dict[str, Any]:
        """Send a private text message via 视频号."""
        return self._post(
            "/finder/postPrivateLetter",
            {"appId": self.app_id, "msgsessionid": str(msgsessionid or "").strip(), "content": str(content or "").strip()},
        )

    def finder_post_private_letter_img(self, *, msgsessionid: str, image_url: str) -> Dict[str, Any]:
        return self._post(
            "/finder/postPrivateLetterImg",
            {"appId": self.app_id, "msgsessionid": str(msgsessionid or "").strip(), "imageUrl": str(image_url or "").strip()},
        )

    def finder_contact_list(self) -> Dict[str, Any]:
        return self._post("/finder/contactList", {"appId": self.app_id})

    def finder_get_msg_session_id(self, *, finder_username: str) -> Dict[str, Any]:
        return self._post(
            "/finder/getMsgSessionId",
            {"appId": self.app_id, "finderUsername": str(finder_username or "").strip()},
        )

    def finder_get_finder_info(self) -> Dict[str, Any]:
        """Get all finder operator identities."""
        return self._post("/finder/getFinderInfo", {"appId": self.app_id})

    def finder_scan_login_channels(self, *, username: str = "") -> Dict[str, Any]:
        """Scan QR login for 视频号助手. Empty username = admin."""
        return self._post("/finder/scanLoginChannels", {"appId": self.app_id, "username": str(username or "").strip()})

    def finder_scan_qrcode(self, *, qr_data: str) -> Dict[str, Any]:
        return self._post("/finder/scanQrCode", {"appId": self.app_id, "qrData": str(qr_data or "").strip()})

    # Finder social actions
    def finder_follow(self, *, finder_username: str) -> Dict[str, Any]:
        return self._post("/finder/follow", {"appId": self.app_id, "finderUsername": str(finder_username or "").strip()})

    def finder_like(self, *, object_id: str) -> Dict[str, Any]:
        return self._post("/finder/idLike", {"appId": self.app_id, "objectId": str(object_id or "").strip()})

    def finder_fav(self, *, object_id: str) -> Dict[str, Any]:
        return self._post("/finder/idFav", {"appId": self.app_id, "objectId": str(object_id or "").strip()})

    def finder_comment(self, *, object_id: str, content: str) -> Dict[str, Any]:
        return self._post(
            "/finder/comment",
            {"appId": self.app_id, "objectId": str(object_id or "").strip(), "content": str(content or "").strip()},
        )

    def finder_browse(self) -> Dict[str, Any]:
        return self._post("/finder/browse", {"appId": self.app_id})

    def finder_get_qrcode(self) -> Dict[str, Any]:
        return self._post("/finder/getQrCode", {"appId": self.app_id})

    def finder_publish(self, *, finder_xml: str) -> Dict[str, Any]:
        """Publish a video to 视频号."""
        return self._post("/finder/publishFinderWeb", {"appId": self.app_id, "finderXml": str(finder_xml or "").strip()})

    def finder_update_profile(self, *, field: str, value: str) -> Dict[str, Any]:
        return self._post(
            "/finder/updateProfile",
            {"appId": self.app_id, str(field or "").strip(): str(value or "").strip()},
        )

    def finder_follow_list(self) -> Dict[str, Any]:
        return self._post("/finder/followList", {"appId": self.app_id})

    def finder_like_fav_list(self) -> Dict[str, Any]:
        return self._post("/finder/likeFavList", {"appId": self.app_id})

    def finder_comment_list(self) -> Dict[str, Any]:
        return self._post("/finder/commentList", {"appId": self.app_id})

    def finder_mention_list(self) -> Dict[str, Any]:
        return self._post("/finder/mentionList", {"appId": self.app_id})

    def finder_user_page(self, *, finder_username: str) -> Dict[str, Any]:
        return self._post("/finder/userPage", {"appId": self.app_id, "finderUsername": str(finder_username or "").strip()})

    def finder_scan_browse(self) -> Dict[str, Any]:
        return self._post("/finder/scanBrowse", {"appId": self.app_id})

    def finder_scan_like(self, *, object_id: str) -> Dict[str, Any]:
        return self._post("/finder/scanLike", {"appId": self.app_id, "objectId": str(object_id or "").strip()})

    def finder_scan_fav(self, *, object_id: str) -> Dict[str, Any]:
        return self._post("/finder/scanFav", {"appId": self.app_id, "objectId": str(object_id or "").strip()})

    def finder_scan_follow(self, *, finder_username: str) -> Dict[str, Any]:
        return self._post("/finder/scanFollow", {"appId": self.app_id, "finderUsername": str(finder_username or "").strip()})

    def finder_scan_comment(self, *, object_id: str, content: str) -> Dict[str, Any]:
        return self._post(
            "/finder/scanComment",
            {"appId": self.app_id, "objectId": str(object_id or "").strip(), "content": str(content or "").strip()},
        )
