# -*- coding: utf-8 -*-
"""method 名 -> recipe 类。submit / monitor / 测试统一入口。"""
from recipe_mae import MAERecipe
from recipe_dino import DINORecipe
from recipe_moco import MoCoRecipe
from recipe_chexworld import CheXWorldRecipe

RECIPES = {
    'mae': MAERecipe,
    'dino': DINORecipe,
    'moco': MoCoRecipe,
    'chexworld': CheXWorldRecipe,
}


def get_recipe(method, e_eq=100):
    if method not in RECIPES:
        raise KeyError(f'未知 method {method}；可用 {list(RECIPES)}')
    return RECIPES[method](e_eq=e_eq)
