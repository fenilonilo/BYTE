# app/api/schemas.py
from __future__ import annotations

from pydantic import BaseModel

from app.domain.gesture_definition import GestureDefinition, MotionSpec, PoseSpec
from app.domain.gestures import Binding, GestureEvent, GestureParams, Vec3


class IncomingMessageSchema(BaseModel):
    sender: str
    content: str
    channel: str
    conversation_id: str | None = None


class OutgoingMessageSchema(BaseModel):
    content: str
    channel: str
    recipient: str


class Vec3Schema(BaseModel):
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

    def to_domain(self) -> Vec3:
        return Vec3(self.x, self.y, self.z)


class GestureParamsSchema(BaseModel):
    points: list[Vec3Schema] = []
    vector: Vec3Schema = Vec3Schema()
    center: Vec3Schema = Vec3Schema()
    radius: float = 0.0
    magnitude: float = 0.0

    def to_domain(self) -> GestureParams:
        return GestureParams(
            points=tuple(p.to_domain() for p in self.points),
            vector=self.vector.to_domain(),
            center=self.center.to_domain(),
            radius=self.radius,
            magnitude=self.magnitude,
        )


class GestureEventSchema(BaseModel):
    gesture: str
    phase: str
    hands: int
    params: GestureParamsSchema
    ts: float

    def to_domain(self) -> GestureEvent:
        return GestureEvent(
            gesture=self.gesture,
            phase=self.phase,
            hands=self.hands,
            params=self.params.to_domain(),
            ts=self.ts,
        )


class PoseSpecSchema(BaseModel):
    shape: str
    hands: int


class MotionSpecSchema(BaseModel):
    type: str
    params: dict[str, object] = {}


class BindingSchema(BaseModel):
    effect: str
    action: str | None = None
    action_params: dict[str, object] = {}


class GestureDefinitionSchema(BaseModel):
    id: str
    name: str
    pose: PoseSpecSchema
    motion: MotionSpecSchema
    binding: BindingSchema

    def to_domain(self) -> GestureDefinition:
        return GestureDefinition(
            id=self.id,
            name=self.name,
            pose=PoseSpec(shape=self.pose.shape, hands=self.pose.hands),
            motion=MotionSpec(type=self.motion.type, params=self.motion.params),
            binding=Binding(
                effect=self.binding.effect,
                action=self.binding.action,
                action_params=self.binding.action_params,
            ),
        )

    @classmethod
    def from_domain(cls, d: GestureDefinition) -> GestureDefinitionSchema:
        return cls(
            id=d.id,
            name=d.name,
            pose=PoseSpecSchema(shape=d.pose.shape, hands=d.pose.hands),
            motion=MotionSpecSchema(type=d.motion.type, params=d.motion.params),
            binding=BindingSchema(
                effect=d.binding.effect,
                action=d.binding.action,
                action_params=d.binding.action_params,
            ),
        )
