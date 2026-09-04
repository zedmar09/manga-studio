from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple


def _load(path: Path) -> Dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Schema must be a JSON object: {path}")
    return data


def _resolve_pointer(root: Dict[str, Any], pointer: str) -> Any:
    current: Any = root
    for raw_part in pointer.lstrip("/").split("/"):
        part = raw_part.replace("~1", "/").replace("~0", "~")
        current = current[part]
    return current


def _type_matches(instance: Any, expected: str) -> bool:
    if expected == "null":
        return instance is None
    if expected == "object":
        return isinstance(instance, dict)
    if expected == "array":
        return isinstance(instance, list)
    if expected == "string":
        return isinstance(instance, str)
    if expected == "boolean":
        return isinstance(instance, bool)
    if expected == "integer":
        return isinstance(instance, int) and not isinstance(instance, bool)
    if expected == "number":
        return isinstance(instance, (int, float)) and not isinstance(instance, bool)
    return True


def _validate(
    instance: Any,
    schema: Dict[str, Any],
    *,
    root_schema: Dict[str, Any],
    schema_path: Path,
    instance_path: str,
) -> List[str]:
    errors: List[str] = []
    if "$ref" in schema:
        reference = schema["$ref"]
        if reference.startswith("#"):
            target = _resolve_pointer(root_schema, reference[1:])
            return _validate(
                instance,
                target,
                root_schema=root_schema,
                schema_path=schema_path,
                instance_path=instance_path,
            )
        reference_file, _, fragment = reference.partition("#")
        target_path = (schema_path.parent / reference_file).resolve()
        target_root = _load(target_path)
        target = _resolve_pointer(target_root, fragment) if fragment else target_root
        return _validate(
            instance,
            target,
            root_schema=target_root,
            schema_path=target_path,
            instance_path=instance_path,
        )

    if "anyOf" in schema:
        alternatives = [
            _validate(instance, item, root_schema=root_schema, schema_path=schema_path, instance_path=instance_path)
            for item in schema["anyOf"]
        ]
        if not any(not item_errors for item_errors in alternatives):
            errors.append(f"{instance_path} does not match any allowed schema")
            return errors

    for item in schema.get("allOf", []):
        errors.extend(_validate(instance, item, root_schema=root_schema, schema_path=schema_path, instance_path=instance_path))

    conditional = schema.get("if")
    if isinstance(conditional, dict):
        condition_errors = _validate(
            instance, conditional, root_schema=root_schema, schema_path=schema_path, instance_path=instance_path
        )
        branch = schema.get("then") if not condition_errors else schema.get("else")
        if isinstance(branch, dict):
            errors.extend(_validate(instance, branch, root_schema=root_schema, schema_path=schema_path, instance_path=instance_path))

    expected_type = schema.get("type")
    if expected_type is not None:
        expected_types = expected_type if isinstance(expected_type, list) else [expected_type]
        if not any(_type_matches(instance, item) for item in expected_types):
            errors.append(f"{instance_path} must be of type {' or '.join(expected_types)}")
            return errors

    if "const" in schema and instance != schema["const"]:
        errors.append(f"{instance_path} must equal {schema['const']!r}")
    if "enum" in schema and instance not in schema["enum"]:
        errors.append(f"{instance_path} has unsupported value {instance!r}")

    if isinstance(instance, str):
        if "minLength" in schema and len(instance) < schema["minLength"]:
            errors.append(f"{instance_path} is shorter than {schema['minLength']} character(s)")
        if "pattern" in schema and re.search(schema["pattern"], instance) is None:
            errors.append(f"{instance_path} does not match required pattern")

    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        if "minimum" in schema and instance < schema["minimum"]:
            errors.append(f"{instance_path} must be at least {schema['minimum']}")
        if "maximum" in schema and instance > schema["maximum"]:
            errors.append(f"{instance_path} must be at most {schema['maximum']}")

    if isinstance(instance, list):
        if "minItems" in schema and len(instance) < schema["minItems"]:
            errors.append(f"{instance_path} must contain at least {schema['minItems']} item(s)")
        if schema.get("uniqueItems"):
            encoded = [json.dumps(item, sort_keys=True) for item in instance]
            if len(encoded) != len(set(encoded)):
                errors.append(f"{instance_path} must contain unique items")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(instance):
                errors.extend(_validate(
                    item,
                    item_schema,
                    root_schema=root_schema,
                    schema_path=schema_path,
                    instance_path=f"{instance_path}[{index}]",
                ))
        contains = schema.get("contains")
        if isinstance(contains, dict):
            if not any(
                not _validate(item, contains, root_schema=root_schema, schema_path=schema_path, instance_path=instance_path)
                for item in instance
            ):
                errors.append(f"{instance_path} does not contain a required item")

    if isinstance(instance, dict):
        required = schema.get("required", [])
        for key in required:
            if key not in instance:
                errors.append(f"{instance_path} is missing required property '{key}'")
        properties = schema.get("properties", {})
        if isinstance(properties, dict):
            for key, property_schema in properties.items():
                if key in instance and isinstance(property_schema, dict):
                    errors.extend(_validate(
                        instance[key],
                        property_schema,
                        root_schema=root_schema,
                        schema_path=schema_path,
                        instance_path=f"{instance_path}.{key}",
                    ))
            if schema.get("additionalProperties") is False:
                for key in sorted(set(instance) - set(properties)):
                    errors.append(f"{instance_path} has unexpected property '{key}'")
    return errors


def validate_instance(instance: Any, schema_path: Path) -> List[str]:
    schema_path = schema_path.resolve()
    root = _load(schema_path)
    return _validate(instance, root, root_schema=root, schema_path=schema_path, instance_path="$" )


def validate_json_file(instance_path: Path, schema_path: Path) -> List[str]:
    instance = json.loads(instance_path.read_text(encoding="utf-8"))
    return validate_instance(instance, schema_path)
