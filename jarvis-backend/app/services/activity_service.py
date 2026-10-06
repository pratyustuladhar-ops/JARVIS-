from datetime import datetime
from typing import List, Optional
from sqlalchemy.orm import Session
from app.models.activity import Activity


class ActivityService:
    def get_recent(self, db: Session, limit: int = 10) -> List[Activity]:
        return db.query(Activity).order_by(Activity.timestamp.desc()).limit(limit).all()

    def record_activity(
        self,
        db: Session,
        event_type: str,
        title: str,
        description: str,
        status: str = "INFO",
        metadata_json: Optional[str] = None
    ) -> Activity:
        activity = Activity(
            event_type=event_type,
            title=title,
            description=description,
            status=status,
            timestamp=datetime.utcnow(),
            metadata_json=metadata_json
        )
        db.add(activity)
        db.commit()
        db.refresh(activity)
        return activity


activity_service = ActivityService()
