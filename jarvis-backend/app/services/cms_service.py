from typing import List, Optional, Dict, Any
import json
from sqlalchemy.orm import Session
from app.models.cms import CMSConfig
from app.schemas.cms import CMSConfigCreate, CMSConfigUpdate


class CMSService:
    def get_all(self, db: Session, category: Optional[str] = None, only_active: bool = True) -> List[CMSConfig]:
        query = db.query(CMSConfig)
        if only_active:
            query = query.filter(CMSConfig.is_active.is_(True))
        if category:
            query = query.filter(CMSConfig.category == category)
        return query.order_by(CMSConfig.category, CMSConfig.key).all()

    def get_by_id(self, db: Session, config_id: int) -> Optional[CMSConfig]:
        return db.query(CMSConfig).filter(CMSConfig.id == config_id).first()

    def get_by_key(self, db: Session, key: str) -> Optional[CMSConfig]:
        return db.query(CMSConfig).filter(CMSConfig.key == key).first()

    def get_value(self, db: Session, key: str, default: Any = None) -> Any:
        cfg = self.get_by_key(db, key)
        if not cfg or not cfg.is_active:
            return default
        if cfg.type == "boolean":
            return cfg.value.lower() in ("true", "1", "yes")
        elif cfg.type == "number":
            try:
                return float(cfg.value) if "." in cfg.value else int(cfg.value)
            except ValueError:
                return cfg.value
        elif cfg.type == "json":
            try:
                return json.loads(cfg.value)
            except Exception:
                return cfg.value
        return cfg.value

    def create(self, db: Session, config_in: CMSConfigCreate) -> CMSConfig:
        existing = self.get_by_key(db, config_in.key)
        if existing:
            # Update existing
            for field, value in config_in.model_dump(exclude_unset=True).items():
                setattr(existing, field, value)
            db.commit()
            db.refresh(existing)
            return existing

        config = CMSConfig(**config_in.model_dump())
        db.add(config)
        db.commit()
        db.refresh(config)
        return config

    def update(self, db: Session, config_id: int, config_in: CMSConfigUpdate) -> Optional[CMSConfig]:
        config = self.get_by_id(db, config_id)
        if not config:
            return None
        update_data = config_in.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(config, field, value)
        db.commit()
        db.refresh(config)
        return config

    def delete(self, db: Session, config_id: int) -> bool:
        config = self.get_by_id(db, config_id)
        if not config:
            return False
        db.delete(config)
        db.commit()
        return True

    def get_content_map(self, db: Session) -> Dict[str, Any]:
        """Returns a nested dictionary of all active configurations grouped by category."""
        configs = self.get_all(db, only_active=True)
        content_map: Dict[str, Any] = {}
        for c in configs:
            cat = c.category or "general"
            if cat not in content_map:
                content_map[cat] = {}
            content_map[cat][c.key] = self.get_value(db, c.key)
        return content_map


cms_service = CMSService()
