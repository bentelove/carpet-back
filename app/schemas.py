from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, EmailStr, Field, HttpUrl, model_validator

class Image(BaseModel):
    url: HttpUrl
    alt: str = Field(min_length=1, max_length=200)

class ProductInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    slug: str = Field(pattern=r'^[a-z0-9]+(?:-[a-z0-9]+)*$', max_length=160)
    name: str = Field(min_length=1, max_length=250)
    description: str = Field(default='', max_length=10000)
    style: str = Field(min_length=1, max_length=60)
    color: str = Field(min_length=1, max_length=100)
    colorCode: str | None = Field(default=None, max_length=60)
    countryCode: str | None = Field(default=None, pattern=r'^[A-Z]{2}$')
    images: list[Image] = Field(default_factory=list, max_length=20)
    badge: str | None = Field(default=None, max_length=60)
    isActive: bool = True
    popularity: int = Field(default=0, ge=0)

class ProductPatch(ProductInput):
    slug: str | None = Field(default=None, pattern=r'^[a-z0-9]+(?:-[a-z0-9]+)*$', max_length=160)
    name: str | None = None
    style: str | None = None
    color: str | None = None

class VariantInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    sku: str = Field(min_length=1, max_length=100)
    sizeLabel: str = Field(min_length=1, max_length=100)
    sizeCode: str = Field(min_length=1, pattern=r'^[a-z0-9-]+$', max_length=100)
    lengthCm: int | None = Field(default=None, gt=0)
    widthCm: int | None = Field(default=None, gt=0)
    diameterCm: int | None = Field(default=None, gt=0)
    price: int = Field(ge=0)
    oldPrice: int | None = Field(default=None, ge=0)
    stockQuantity: int = Field(ge=0)
    isActive: bool = True

    @model_validator(mode='after')
    def check(self):
        if self.oldPrice is not None and self.oldPrice <= self.price:
            raise ValueError('oldPrice must exceed price')
        if self.diameterCm is not None and (self.lengthCm is not None or self.widthCm is not None):
            raise ValueError('diameter and rectangular dimensions cannot be combined')
        return self

class VariantPatch(BaseModel):
    model_config = ConfigDict(extra='forbid')
    sku: str | None = Field(default=None, min_length=1, max_length=100)
    sizeLabel: str | None = Field(default=None, min_length=1, max_length=100)
    sizeCode: str | None = Field(default=None, min_length=1, pattern=r'^[a-z0-9-]+$', max_length=100)
    lengthCm: int | None = Field(default=None, gt=0)
    widthCm: int | None = Field(default=None, gt=0)
    diameterCm: int | None = Field(default=None, gt=0)
    price: int | None = Field(default=None, ge=0)
    oldPrice: int | None = Field(default=None, ge=0)
    stockQuantity: int | None = Field(default=None, ge=0)
    isActive: bool | None = None

class ItemIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    variantId: str = Field(pattern=r'^[0-9a-fA-F-]{36}$')
    quantity: int = Field(ge=1, le=100)

class QuantityIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    quantity: int = Field(ge=1, le=100)

class Address(BaseModel):
    model_config = ConfigDict(extra='forbid')
    city: str = Field(min_length=1, max_length=150)
    street: str = Field(min_length=1, max_length=200)
    house: str = Field(min_length=1, max_length=30)
    apartment: str | None = Field(default=None, max_length=30)
    postalCode: str | None = Field(default=None, pattern=r'^\d{6}$')

class QuoteIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    address: Address
    deliveryMethod: Literal['manual_delivery']

class OrderIn(QuoteIn):
    customerName: str = Field(min_length=2, max_length=150)
    phone: str = Field(pattern=r'^\+?[0-9 ()-]{10,25}$')
    email: EmailStr | None = None
    paymentMethod: Literal['on_delivery', 'manual_confirmation']
    comment: str | None = Field(default=None, max_length=2000)
    personalDataConsent: Literal[True]

class StatusIn(BaseModel):
    status: Literal['new', 'confirmed', 'cancelled', 'fulfilled']
