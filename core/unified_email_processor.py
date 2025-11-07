"""
Unified Email Processor
Xử lý email thống nhất cho cả polling và webhook
Đảm bảo không duplicate, không bỏ sót
"""
import json
import os
import base64
import httpx
from typing import List, Dict, Optional
from core.session_manager import session_manager
from utils.config import (
    ATTACH_DIR,
    SPAM_PATTERNS
)

class EmailProcessor:
    """Core processor xử lý email"""
    
    def __init__(self, token: str):
        self.token = token
        self.headers = {"Authorization": f"Bearer {token}"}
        self.client = httpx.Client(headers=self.headers, timeout=10)
        os.makedirs(ATTACH_DIR, exist_ok=True)
    
    def process_email(self, message: Dict, source: str = "unknown") -> Optional[Dict]:
        """Xử lý một email và trả về metadata nếu thành công."""
        msg_id = message.get("id")
        if not msg_id:
            print("[EmailProcessor] Missing message ID")
            return None

        if session_manager.is_email_processed(msg_id):
            print(f"[EmailProcessor] [{source}] Email {msg_id} already processed")
            return None

        subject = message.get("subject", "")
        sender = message.get("from", {}).get("emailAddress", {}).get("address", "")
        
        print(f"[EmailProcessor] [{source}] Processing: {msg_id}")
        print(f"  Subject: {subject}")
        print(f"  From: {sender}")

        try:
            if self._is_spam(sender):
                print("[EmailProcessor] SPAM detected, moving to junk")
                self._move_to_junk(msg_id)
                session_manager.register_processed_email(msg_id)
                return None  # Spam emails don't produce metadata

            self._save_attachments(msg_id)
            
            # This now returns the metadata payload
            metadata = self._prepare_persistence_payload(message)
            
            session_manager.register_processed_email(msg_id)
            
            print(f"[EmailProcessor] [{source}] Successfully processed: {msg_id}")
            return metadata

        except Exception as e:
            print(f"[EmailProcessor] [{source}] Error processing {msg_id}: {e}")
            return None
    
    def batch_process_emails(self, messages: List[Dict], source: str = "polling") -> Dict:
        """Xử lý batch emails"""
        result = {
            "total": len(messages),
            "success": 0,
            "failed": 0,
            "skipped": 0
        }
        
        for msg in messages:
            msg_id = msg.get("id")
            
            if session_manager.is_email_processed(msg_id):
                result["skipped"] += 1
                continue
            
            session_manager.register_pending_email(msg_id)
            
            if self.process_email(msg, source=source):
                result["success"] += 1
            else:
                result["failed"] += 1
        
        return result
    
    def _is_spam(self, sender: str) -> bool:
        """Kiểm tra spam"""
        return any(pattern in sender for pattern in SPAM_PATTERNS)
    
    def _move_to_junk(self, message_id: str):
        """Di chuyển email vào Junk"""
        move_url = f"https://graph.microsoft.com/v1.0/me/messages/{message_id}/move"
        move_body = {"destinationId": "junkemail"}
        try:
            self.client.post(move_url, json=move_body)
        except Exception as e:
            print(f"[EmailProcessor] Move to junk error: {e}")
    
    def _save_attachments(self, message_id: str):
        """Lưu file đính kèm"""
        url = f"https://graph.microsoft.com/v1.0/me/messages/{message_id}/attachments"
        try:
            resp = self.client.get(url)
            if resp.status_code != 200:
                return
            
            attachments = resp.json().get("value", [])
            for att in attachments:
                if att.get("@odata.type") == "#microsoft.graph.fileAttachment":
                    file_name = att.get("name", "unknown_file")
                    content_bytes = att.get("contentBytes")
                    
                    if content_bytes:
                        _, ext = os.path.splitext(file_name)
                        if not ext:
                            ext = ".bin"
                        
                        att_path = os.path.join(ATTACH_DIR, f"{message_id}{ext}")
                        with open(att_path, "wb") as f:
                            f.write(base64.b64decode(content_bytes))
                        
                        print(f"[EmailProcessor] Attachment saved: {att_path}")
        except Exception as e:
            print(f"[EmailProcessor] Save attachments error: {e}")
    

    
    def _prepare_persistence_payload(self, message: Dict) -> Dict:
        """Chuẩn bị metadata để gửi đến MS4 Persistence."""
        metadata = {
            "id": message.get("id"),
            "subject": message.get("subject"),
            "hasAttachments": message.get("hasAttachments", False),
            "sender": message.get("from", {}).get("emailAddress", {}).get("address", ""),
            "receivedDateTime": message.get("receivedDateTime"),
            "raw_message": json.dumps(message)
        }
        return metadata
    
    def close(self):
        """Closes the httpx client."""
        self.client.close()
        print("[EmailProcessor] HTTPX client closed.")