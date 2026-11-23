from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class UiObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)

    role: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9-]*$")
    name: str = Field(max_length=180)
    width: float = Field(strict=True, ge=0, le=1000000)
    height: float = Field(strict=True, ge=0, le=1000000)
    visible: bool = Field(strict=True)
    enabled: bool = Field(strict=True)
    checked: bool | None = Field(default=None, strict=True)
    observed_at: AwareDatetime
