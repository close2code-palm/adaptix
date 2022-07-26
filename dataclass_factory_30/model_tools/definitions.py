# pylint: disable=invalid-overridden-method,arguments-differ
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Generic, Hashable, Mapping, MutableMapping, Optional, TypeVar, Union

from ..common import Catchable, TypeHint, VarTuple
from ..struct_path import Attr, PathElement
from ..utils import SingletonMeta, pairs

T = TypeVar('T')


class NoDefault(metaclass=SingletonMeta):
    pass


@dataclass(frozen=True)
class DefaultValue(Generic[T]):
    value: T

    def __hash__(self):
        try:
            return hash(self.value)
        except TypeError:
            return 236  # some random number that fits in byte


@dataclass(frozen=True)
class DefaultFactory(Generic[T]):
    factory: Callable[[], T]


Default = Union[NoDefault, DefaultValue[T], DefaultFactory[T]]


class Accessor(Hashable, ABC):
    @property
    @abstractmethod
    def getter(self) -> Callable[[Any], Any]:
        pass

    @property
    @abstractmethod
    def access_error(self) -> Optional[Catchable]:
        pass

    @property
    @abstractmethod
    def path_element(self) -> PathElement:
        pass


class DescriptorAccessor(Accessor, ABC):
    # pylint: disable=invalid-overridden-method,arguments-differ
    # Dataclasses delete all field() attributes if there is no default value.
    # So, if setup it as abstract property,
    # constructor can not set value to attribute due property has no setter
    attr_name: str

    # noinspection PyMethodOverriding
    def getter(self, obj):
        return getattr(obj, self.attr_name)

    @property
    def path_element(self) -> PathElement:
        return Attr(self.attr_name)


@dataclass(frozen=True)
class PropertyAccessor(DescriptorAccessor):  # TODO: make up more appropriate name
    attr_name: str
    access_error: Optional[Catchable] = field(default=None)

    def __hash__(self):
        return hash((self.attr_name, self.access_error))


@dataclass(frozen=True)
class AttrAccessor(DescriptorAccessor):
    attr_name: str
    is_required: bool

    @property
    def access_error(self) -> Optional[Catchable]:
        return None if self.is_required else AttributeError

    def __hash__(self):
        return hash((self.attr_name, self.is_required))


@dataclass(frozen=True)
class ItemAccessor(Accessor):
    item_name: str
    is_required: bool

    # noinspection PyMethodOverriding
    def getter(self, obj):
        return obj[self.item_name]

    @property
    def access_error(self) -> Optional[Catchable]:
        return None if self.is_required else KeyError

    @property
    def path_element(self) -> PathElement:
        return self.item_name

    def __hash__(self):
        return hash((self.item_name, self.is_required))


@dataclass(frozen=True)
class BaseField:
    type: TypeHint
    name: str
    default: Default
    # Mapping almost never defines __hash__,
    # so it will be more convenient to exclude this field
    # from hash computation
    metadata: Mapping[Any, Any] = field(hash=False)

    def __post_init__(self):
        if not self.name.isidentifier():
            raise ValueError(f"name of field must be python identifier, now it is a {self.name!r}")


class ParamKind(Enum):
    POS_ONLY = 0
    POS_OR_KW = 1
    KW_ONLY = 3  # 2 is for VAR_POS


@dataclass(frozen=True)
class InputField(BaseField):
    is_required: bool
    param_kind: ParamKind
    param_name: str

    @property
    def is_optional(self):
        return not self.is_required

    def __post_init__(self):
        super().__post_init__()
        if not self.param_name.isidentifier():
            raise ValueError(f"param_name must be python identifier, now it is a {self.param_name!r}")

        if self.param_kind == ParamKind.POS_ONLY and not self.is_required:
            raise ValueError(f"{type(self)} can not be positional only and optional")


@dataclass(frozen=True)
class OutputField(BaseField):
    accessor: Accessor

    @property
    def is_optional(self) -> bool:
        return not self.is_required

    @property
    def is_required(self) -> bool:
        return self.accessor.access_error is None


class ExtraKwargs(metaclass=SingletonMeta):
    pass


@dataclass(frozen=True)
class ExtraTargets:
    fields: VarTuple[str]


@dataclass(frozen=True)
class ExtraSaturate(Generic[T]):
    func: Callable[[T, MutableMapping[str, Any]], None]


@dataclass(frozen=True)
class ExtraExtract(Generic[T]):
    func: Callable[[T], Mapping[str, Any]]


BaseFigureExtra = Union[None, ExtraKwargs, ExtraTargets, ExtraSaturate[T], ExtraExtract[T]]


@dataclass(frozen=True)
class BaseFigure:
    """Signature of class. Divided into 2 parts: input and output.
    See doc :class InputFigure: and :class OutputFigure: for more details
    """
    fields: VarTuple[BaseField]
    extra: BaseFigureExtra

    def _validate(self):
        field_names = {fld.name for fld in self.fields}
        if len(field_names) != len(self.fields):
            duplicates = {
                fld.name for fld in self.fields
                if fld.name in field_names
            }
            raise ValueError(f"Field names {duplicates} are duplicated")

        if isinstance(self.extra, ExtraTargets):
            wild_targets = [
                target for target in self.extra.fields
                if target not in field_names
            ]

            if wild_targets:
                raise ValueError(
                    f"ExtraTargets {wild_targets} are attached to non-existing fields"
                )

    def __post_init__(self):
        self._validate()


InpFigureExtra = Union[None, ExtraKwargs, ExtraTargets, ExtraSaturate[T]]


@dataclass(frozen=True)
class InputFigure(BaseFigure, Generic[T]):
    """Description of desired object creation

    :param constructor: callable that produces an instance of the class.
    :param fields: parameters of the constructor
    :param extra: the way of passing extra data (data that does not map to any field)
        None means that constructor can not take any extra data.
        ExtraKwargs means that all extra data could be passed as additional keyword parameters
        ExtraTargets means that all extra data could be passed to corresponding fields.
        ExtraSaturate means that after constructing object specified function will be applied
    """
    fields: VarTuple[InputField]
    extra: InpFigureExtra[T]
    constructor: Callable[..., T]

    def _validate(self):
        super()._validate()

        param_names = {fld.param_name for fld in self.fields}
        if len(param_names) != len(self.fields):
            duplicates = {
                fld.param_name for fld in self.fields
                if fld.param_name in param_names
            }
            raise ValueError(f"Param names {duplicates} are duplicated")

        for past, current in pairs(self.fields):
            if past.param_kind.value > current.param_kind.value:
                raise ValueError(
                    f"Inconsistent order of fields,"
                    f" {current.param_kind} must be after {past.param_kind}"
                )

            if (
                past.is_optional
                and current.is_required
                and current.param_kind != ParamKind.KW_ONLY
            ):
                raise ValueError(
                    f"All not required fields must be after required ones"
                    f" except {ParamKind.KW_ONLY} fields"
                )


OutFigureExtra = Union[None, ExtraTargets, ExtraExtract[T]]


@dataclass(frozen=True)
class OutputFigure(BaseFigure):
    """Description of extraction data from an object

    :param fields: fields (can be not only attributes) of object
    :param extra: the way of extracting extra data (data that does not map to any field)
        None means that there is no way to get extra data
        ExtraTargets means extra data will be extracted from corresponding fields and will be merged
        ExtraExtract means that extra data will be taken by applying a specified function
    """
    fields: VarTuple[OutputField]
    extra: OutFigureExtra


class IntrospectionError(Exception):
    pass


class NoTargetPackage(IntrospectionError):
    pass
