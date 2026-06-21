"""組織與產品階層：site → product → sku。

依據 data-model-and-storage-spec §2.1–2.3。
external_code：對外語言中立業務碼；name_zh/name_en：i18n。
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ddm_v2.models.v2.base import Base, TimestampMixin, uuid_pk


class Site(Base, TimestampMixin):
    __tablename__ = "sites"

    id: Mapped[UUID] = uuid_pk()
    external_code: Mapped[str | None] = mapped_column(Text, unique=True)
    name_zh: Mapped[str] = mapped_column(Text, nullable=False)
    name_en: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("TRUE"))

    products: Mapped[list[Product]] = relationship(back_populates="site")


class Product(Base, TimestampMixin):
    __tablename__ = "products"

    id: Mapped[UUID] = uuid_pk()
    site_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("sites.id", ondelete="RESTRICT"), nullable=False)
    external_code: Mapped[str | None] = mapped_column(Text, unique=True)
    name_zh: Mapped[str] = mapped_column(Text, nullable=False)
    name_en: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("TRUE"))

    site: Mapped[Site] = relationship(back_populates="products")
    skus: Mapped[list[Sku]] = relationship(back_populates="product")


class Sku(Base, TimestampMixin):
    __tablename__ = "skus"

    id: Mapped[UUID] = uuid_pk()
    product_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False)
    sku_code: Mapped[str] = mapped_column(Text, nullable=False)  # 常即 external_code，如 HDL5X_AVERY05
    name_zh: Mapped[str | None] = mapped_column(Text)
    name_en: Mapped[str | None] = mapped_column(Text)
    attributes: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("TRUE"))

    product: Mapped[Product] = relationship(back_populates="skus")

    __table_args__ = (UniqueConstraint("product_id", "sku_code", name="uq_skus_product_id_sku_code"),)
