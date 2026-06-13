"""Operator registry."""

from . import align, arrange, selection, texel, unwrap, utility

MODULES = [align, arrange, selection, texel, unwrap, utility]


def all_actions():
    actions = []
    for module in MODULES:
        actions.extend(module.ACTIONS)
    return actions

