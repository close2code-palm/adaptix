from collections import defaultdict
from dataclasses import dataclass
from typing import Callable, DefaultDict, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple, TypeVar, Union

from ...common import VarTuple
from ...model_tools.definitions import (
    BaseField,
    BaseShape,
    DefaultFactory,
    DefaultFactoryWithSelf,
    DefaultValue,
    InputField,
    NoDefault,
    OutputField,
)
from ...name_style import NameStyle, convert_snake_style
from ...provider.essential import CannotProvide, Mediator, Provider
from ...provider.overlay_schema import Overlay, Schema, provide_schema
from ...provider.request_cls import LocatedRequest, TypeHintLoc
from ...provider.request_filtering import ExtraStackMediator, RequestChecker
from ...retort.operating_retort import OperatingRetort
from ...special_cases_optimization import with_default_clause
from ...utils import Omittable, get_prefix_groups
from ..model.crown_definitions import (
    BaseFieldCrown,
    BaseNameLayoutRequest,
    DictExtraPolicy,
    ExtraCollect,
    ExtraExtract,
    ExtraForbid,
    ExtraKwargs,
    ExtraSaturate,
    ExtraSkip,
    ExtraTargets,
    InpExtraMove,
    InpFieldCrown,
    InpNoneCrown,
    InputNameLayoutRequest,
    LeafBaseCrown,
    LeafInpCrown,
    LeafOutCrown,
    OutExtraMove,
    OutFieldCrown,
    OutNoneCrown,
    OutputNameLayoutRequest,
    Sieve,
)
from ..model.fields import field_to_loc_map
from .base import (
    ExtraIn,
    ExtraMoveMaker,
    ExtraOut,
    ExtraPoliciesMaker,
    Key,
    KeyPath,
    PathsTo,
    SievesMaker,
    StructureMaker,
)
from .name_mapping import NameMappingFilterRequest, NameMappingRequest


@dataclass(frozen=True)
class StructureSchema(Schema):
    skip: RequestChecker
    only: RequestChecker

    map: VarTuple[Provider]
    trim_trailing_underscore: bool
    name_style: Optional[NameStyle]
    as_list: bool


@dataclass(frozen=True)
class StructureOverlay(Overlay[StructureSchema]):
    skip: Omittable[RequestChecker]
    only: Omittable[RequestChecker]

    map: Omittable[VarTuple[Provider]]
    trim_trailing_underscore: Omittable[bool]
    name_style: Omittable[Optional[NameStyle]]
    as_list: Omittable[bool]

    def _merge_map(self, old: VarTuple[Provider], new: VarTuple[Provider]) -> VarTuple[Provider]:
        return new + old


AnyField = Union[InputField, OutputField]
LeafCr = TypeVar('LeafCr', bound=LeafBaseCrown)
FieldCr = TypeVar('FieldCr', bound=BaseFieldCrown)
F = TypeVar('F', bound=BaseField)
FieldAndPath = Tuple[F, Optional[KeyPath]]


def apply_rc(
    mediator: Mediator,
    request: BaseNameLayoutRequest,
    request_checker: RequestChecker,
    field: BaseField,
) -> bool:
    owner_type = request.loc_map[TypeHintLoc].type
    filter_request = NameMappingFilterRequest(loc_map=field_to_loc_map(owner_type, field))
    try:
        request_checker.check_request(
            ExtraStackMediator(mediator, [filter_request]),
            filter_request,
        )
    except CannotProvide:
        return False
    return True


class BuiltinStructureMaker(StructureMaker):
    def _generate_key(self, schema: StructureSchema, shape: BaseShape, field: BaseField) -> Key:
        if schema.as_list:
            return shape.fields.index(field)

        name = field.id
        if schema.trim_trailing_underscore and name.endswith('_') and not name.endswith('__'):
            name = name.rstrip('_')
        if schema.name_style is not None:
            name = convert_snake_style(name, schema.name_style)
        return name

    def _create_map_provider(self, schema: StructureSchema) -> Provider:
        return OperatingRetort(recipe=schema.map)

    def _map_fields(
        self,
        mediator: Mediator,
        request: BaseNameLayoutRequest,
        schema: StructureSchema,
        extra_move: Union[InpExtraMove, OutExtraMove],
    ) -> Iterable[FieldAndPath]:
        extra_targets = extra_move.fields if isinstance(extra_move, ExtraTargets) else ()
        map_provider = self._create_map_provider(schema)
        for field in request.shape.fields:
            if field.id in extra_targets:
                continue

            generated_key = self._generate_key(schema, request.shape, field)
            try:
                path = map_provider.apply_provider(
                    mediator,
                    NameMappingRequest(
                        shape=request.shape,
                        field=field,
                        generated_key=generated_key,
                        loc_map=field_to_loc_map(request.loc_map[TypeHintLoc].type, field),
                    )
                )
            except CannotProvide:
                path = (generated_key, )

            if path is None:
                yield field, None
            elif (
                not apply_rc(mediator, request, schema.skip, field)
                and apply_rc(mediator, request, schema.only, field)
            ):
                yield field, path
            else:
                yield field, None

    def _validate_structure(
        self,
        request: LocatedRequest,
        fields_to_paths: Iterable[FieldAndPath],
    ) -> None:
        paths_to_fields: DefaultDict[KeyPath, List[AnyField]] = defaultdict(list)
        for field, path in fields_to_paths:
            if path is not None:
                paths_to_fields[path].append(field)

        duplicates = {
            path: [field.id for field in fields]
            for path, fields in paths_to_fields.items()
            if len(fields) > 1
        }
        if duplicates:
            raise CannotProvide(
                f"Paths {duplicates} pointed to several fields",
                is_terminal=True,
                is_demonstrative=True,
            )

        prefix_groups = get_prefix_groups([path for field, path in fields_to_paths if path is not None])
        if prefix_groups:
            details = '. '.join(
                # pylint: disable=consider-using-f-string
                'Path {prefix} (field {prefix_field!r}) is prefix of {paths}'.format(
                    prefix=list(prefix),
                    prefix_field=paths_to_fields[prefix][0].id,
                    paths=', '.join(
                        # pylint: disable=consider-using-f-string
                        '{path} (field {path_field!r})'.format(
                            path=list(path),
                            path_field=paths_to_fields[path][0].id,
                        )
                        for path in paths
                    ),
                )
                for prefix, paths in prefix_groups
            )
            raise CannotProvide(
                'Path to the field must not be a prefix of another path. ' + details,
                is_terminal=True,
                is_demonstrative=True,
            )

        optional_fields_at_list = [
            field.id
            for field, path in fields_to_paths
            if path is not None and field.is_optional and isinstance(path[-1], int)
        ]
        if optional_fields_at_list:
            raise CannotProvide(
                f"Optional fields {optional_fields_at_list} can not be mapped to list elements",
                is_terminal=True,
                is_demonstrative=True,
            )

    def _iterate_sub_paths(self, paths: Iterable[KeyPath]) -> Iterable[Tuple[KeyPath, Key]]:
        yielded: Set[Tuple[KeyPath, Key]] = set()
        for path in paths:
            for i in range(len(path) - 1, -1, -1):
                result = path[:i], path[i]
                if result in yielded:
                    break

                yielded.add(result)
                yield result

    def _get_paths_to_list(self, request: LocatedRequest, paths: Iterable[KeyPath]) -> Mapping[KeyPath, Set[int]]:
        paths_to_lists: DefaultDict[KeyPath, Set[int]] = defaultdict(set)
        paths_to_dicts: Set[KeyPath] = set()
        for sub_path, key in self._iterate_sub_paths(paths):
            if isinstance(key, int):
                if sub_path in paths_to_dicts:
                    raise CannotProvide(
                        f"Inconsistent path elements at {sub_path}",
                        is_terminal=True,
                        is_demonstrative=True,
                    )

                paths_to_lists[sub_path].add(key)
            else:
                if sub_path in paths_to_lists:
                    raise CannotProvide(
                        f"Inconsistent path elements at {sub_path}",
                        is_terminal=True,
                        is_demonstrative=True,
                    )

                paths_to_dicts.add(sub_path)

        return paths_to_lists

    def _make_paths_to_leaves(
        self,
        request: LocatedRequest,
        fields_to_paths: Iterable[FieldAndPath],
        field_crown: Callable[[str], FieldCr],
        gaps_filler: Callable[[KeyPath], LeafCr],
    ) -> PathsTo[Union[FieldCr, LeafCr]]:
        paths_to_leaves: Dict[KeyPath, Union[FieldCr, LeafCr]] = {
            path: field_crown(field.id)
            for field, path in fields_to_paths
            if path is not None
        }

        paths_to_lists = self._get_paths_to_list(request, paths_to_leaves.keys())
        for path, indexes in paths_to_lists.items():
            for i in range(max(indexes)):
                if i not in indexes:
                    complete_path = path + (i, )
                    paths_to_leaves[complete_path] = gaps_filler(complete_path)

        return paths_to_leaves

    def _fill_input_gap(self, path: KeyPath) -> LeafInpCrown:
        return InpNoneCrown()

    def _fill_output_gap(self, path: KeyPath) -> LeafOutCrown:
        return OutNoneCrown(placeholder=DefaultValue(None))

    def make_inp_structure(
        self,
        mediator: Mediator,
        request: InputNameLayoutRequest,
        extra_move: InpExtraMove,
    ) -> PathsTo[LeafInpCrown]:
        schema = provide_schema(StructureOverlay, mediator, request.loc_map)
        fields_to_paths: List[FieldAndPath[InputField]] = list(
            self._map_fields(mediator, request, schema, extra_move)
        )
        skipped_required_fields = [
            field.id
            for field, path in fields_to_paths
            if path is None and field.is_required
        ]
        if skipped_required_fields:
            raise CannotProvide(
                f"Required fields {skipped_required_fields} are skipped",
                is_terminal=True,
                is_demonstrative=True,
            )
        paths_to_leaves = self._make_paths_to_leaves(request, fields_to_paths, InpFieldCrown, self._fill_input_gap)
        self._validate_structure(request, fields_to_paths)
        return paths_to_leaves

    def make_out_structure(
        self,
        mediator: Mediator,
        request: OutputNameLayoutRequest,
        extra_move: OutExtraMove,
    ) -> PathsTo[LeafOutCrown]:
        schema = provide_schema(StructureOverlay, mediator, request.loc_map)
        fields_to_paths: List[FieldAndPath[OutputField]] = list(
            self._map_fields(mediator, request, schema, extra_move)
        )
        paths_to_leaves = self._make_paths_to_leaves(request, fields_to_paths, OutFieldCrown, self._fill_output_gap)
        self._validate_structure(request, fields_to_paths)
        return paths_to_leaves

    def empty_as_list_inp(self, mediator: Mediator, request: InputNameLayoutRequest) -> bool:
        return provide_schema(StructureOverlay, mediator, request.loc_map).as_list

    def empty_as_list_out(self, mediator: Mediator, request: OutputNameLayoutRequest) -> bool:
        return provide_schema(StructureOverlay, mediator, request.loc_map).as_list


@dataclass(frozen=True)
class SievesSchema(Schema):
    omit_default: RequestChecker


@dataclass(frozen=True)
class SievesOverlay(Overlay[SievesSchema]):
    omit_default: Omittable[RequestChecker]


class BuiltinSievesMaker(SievesMaker):
    def _create_sieve(self, field: OutputField) -> Sieve:
        if isinstance(field.default, DefaultValue):
            default_value = field.default.value
            return with_default_clause(field.default, lambda obj, value: value != default_value)

        if isinstance(field.default, DefaultFactory):
            default_factory = field.default.factory
            return with_default_clause(field.default, lambda obj, value: value != default_factory())

        if isinstance(field.default, DefaultFactoryWithSelf):
            default_factory_with_self = field.default.factory
            return with_default_clause(field.default, lambda obj, value: value != default_factory_with_self(obj))

        raise ValueError

    def make_sieves(
        self,
        mediator: Mediator,
        request: OutputNameLayoutRequest,
        paths_to_leaves: PathsTo[LeafOutCrown],
    ) -> PathsTo[Sieve]:
        schema = provide_schema(SievesOverlay, mediator, request.loc_map)
        result = {}
        for path, leaf in paths_to_leaves.items():
            if isinstance(leaf, OutFieldCrown):
                field = request.shape.fields_dict[leaf.id]
                if field.default != NoDefault() and apply_rc(mediator, request, schema.omit_default, field):
                    result[path] = self._create_sieve(field)
        return result


def _paths_to_branches(paths_to_leaves: PathsTo[LeafBaseCrown]) -> Iterable[Tuple[KeyPath, Key]]:
    yielded_branch_path: Set[KeyPath] = set()
    for path in paths_to_leaves.keys():
        for i in range(len(path) - 1, -2, -1):
            sub_path = path[:i]
            if sub_path in yielded_branch_path:
                break

            yield sub_path, path[i]


@dataclass(frozen=True)
class ExtraMoveAndPoliciesSchema(Schema):
    extra_in: ExtraIn
    extra_out: ExtraOut


@dataclass(frozen=True)
class ExtraMoveAndPoliciesOverlay(Overlay[ExtraMoveAndPoliciesSchema]):
    extra_in: Omittable[ExtraIn]
    extra_out: Omittable[ExtraOut]


class BuiltinExtraMoveAndPoliciesMaker(ExtraMoveMaker, ExtraPoliciesMaker):
    def _create_extra_targets(self, extra: Union[str, Sequence[str]]) -> ExtraTargets:
        if isinstance(extra, str):
            return ExtraTargets((extra,))
        return ExtraTargets(tuple(extra))

    def make_inp_extra_move(
        self,
        mediator: Mediator,
        request: InputNameLayoutRequest,
    ) -> InpExtraMove:
        schema = provide_schema(ExtraMoveAndPoliciesOverlay, mediator, request.loc_map)
        if schema.extra_in in (ExtraForbid(), ExtraSkip()):
            return None
        if schema.extra_in == ExtraKwargs():
            return ExtraKwargs()
        if callable(schema.extra_in):
            return ExtraSaturate(schema.extra_in)
        return self._create_extra_targets(schema.extra_in)  # type: ignore[arg-type]

    def make_out_extra_move(
        self,
        mediator: Mediator,
        request: OutputNameLayoutRequest,
    ) -> OutExtraMove:
        schema = provide_schema(ExtraMoveAndPoliciesOverlay, mediator, request.loc_map)
        if schema.extra_out == ExtraSkip():
            return None
        if callable(schema.extra_out):
            return ExtraExtract(schema.extra_out)
        return self._create_extra_targets(schema.extra_out)  # type: ignore[arg-type]

    def _get_extra_policy(self, schema: ExtraMoveAndPoliciesSchema) -> DictExtraPolicy:
        if schema.extra_in == ExtraSkip():
            return ExtraSkip()
        if schema.extra_in == ExtraForbid():
            return ExtraForbid()
        return ExtraCollect()

    def make_extra_policies(
        self,
        mediator: Mediator,
        request: InputNameLayoutRequest,
        paths_to_leaves: PathsTo[LeafInpCrown],
    ) -> PathsTo[DictExtraPolicy]:
        schema = provide_schema(ExtraMoveAndPoliciesOverlay, mediator, request.loc_map)
        policy = self._get_extra_policy(schema)
        path_to_extra_policy: Dict[KeyPath, DictExtraPolicy] = {
            (): policy,
        }
        for path, key in _paths_to_branches(paths_to_leaves):
            if policy == ExtraCollect() and isinstance(key, int):
                raise CannotProvide(
                    "Can not use collecting extra_in with list mapping",
                    is_terminal=True,
                    is_demonstrative=True,
                )
            path_to_extra_policy[path] = policy
        return path_to_extra_policy
