from sqlalchemy import Boolean, Column, Float, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.core.database import Base


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(150), nullable=False, index=True)
    description = Column(String(500), nullable=True)
    price = Column(Float, nullable=False)
    stock = Column(Integer, nullable=False, default=0)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    image_url = Column(String(2048), nullable=True)
    version = Column(Integer, nullable=False, default=0, server_default="0")
    weight_grams = Column(Integer, nullable=False, default=500, server_default='500')
    height_cm = Column(Integer, nullable=False, default=10, server_default='10')
    width_cm = Column(Integer, nullable=False, default=15, server_default='15')
    length_cm = Column(Integer, nullable=False, default=20, server_default='20')

    category = relationship("Category", back_populates="products")
