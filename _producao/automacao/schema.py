"""Only the JSON Schema vocabulary used by our schema; unsupported keywords fail closed."""
import json
import re

KEYWORDS = {'$schema', '$defs', '$ref', 'title', 'description', 'type', 'const', 'enum',
            'required', 'properties', 'additionalProperties', 'items', 'minItems',
            'maxItems', 'uniqueItems', 'minLength', 'pattern'}

def check_schema(node):
    if set(node) - KEYWORDS:
        raise ValueError(f'Vocabulário não implementado: {set(node) - KEYWORDS}')
    for key in ('$defs', 'properties'):
        for child in node.get(key, {}).values():
            check_schema(child)
    if 'items' in node:
        check_schema(node['items'])

def validate(value, schema):
    check_schema(schema)
    errors = []
    def visit(v, rule, loc):
        if '$ref' in rule:
            ref = rule['$ref']
            if not ref.startswith('#/$defs/'):
                raise ValueError('Referência externa não permitida')
            visit(v, schema['$defs'][ref.split('/')[-1]], loc)
        types = {'object': dict, 'array': list, 'string': str, 'boolean': bool}
        if 'type' in rule and type(v) is not types[rule['type']]:
            errors.append(f'{loc}: tipo incorreto'); return
        if 'const' in rule and v != rule['const']:
            errors.append(f'{loc}: const diferente')
        if 'enum' in rule and v not in rule['enum']:
            errors.append(f'{loc}: valor fora de enum')
        if isinstance(v, dict):
            for k in rule.get('required', []):
                if k not in v:
                    errors.append(f'{loc}.{k}: obrigatório')
            for k, child in v.items():
                if k in rule.get('properties', {}):
                    visit(child, rule['properties'][k], f'{loc}.{k}')
                elif rule.get('additionalProperties') is False:
                    errors.append(f'{loc}.{k}: campo não permitido')
        if isinstance(v, list):
            if not rule.get('minItems', 0) <= len(v) <= rule.get('maxItems', float('inf')):
                errors.append(f'{loc}: quantidade inválida')
            if rule.get('uniqueItems') and len({json.dumps(x, sort_keys=True) for x in v}) != len(v):
                errors.append(f'{loc}: duplicatas')
            if 'items' in rule:
                for i, child in enumerate(v):
                    visit(child, rule['items'], f'{loc}[{i}]')
        if isinstance(v, str):
            if len(v) < rule.get('minLength', 0) or ('pattern' in rule and not re.search(rule['pattern'], v)):
                errors.append(f'{loc}: texto/formato inválido')
    visit(value, schema, '$')
    return errors
