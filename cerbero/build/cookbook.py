# cerbero - a multi-platform build system for Open Source software
# Copyright (C) 2012 Andoni Morales Alastruey <ylatuya@gmail.com>
#
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Library General Public
# License as published by the Free Software Foundation; either
# version 2 of the License, or (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Library General Public License for more details.
#
# You should have received a copy of the GNU Library General Public
# License along with this library; if not, write to the
# Free Software Foundation, Inc., 59 Temple Place - Suite 330,
# Boston, MA 02111-1307, USA.

import os
import pickle
import time

from cerbero.config import CONFIG_DIR, Platform, Architecture, Distro, DistroVersion
from cerbero.build.build import BuildType
from cerbero.build.source import SourceType
from cerbero.errors import FatalError
from cerbero.utils import _
from cerbero.utils import messages as m
from cerbero.build import recipe as crecipe


COOKBOOK_NAME = 'cookbook'
COOKBOOK_FILE = os.path.join(CONFIG_DIR, COOKBOOK_NAME)


class RecipeStatus (object):
    '''
    Stores the current build status of a L{cerbero.recipe.Recipe}

    @ivar steps: list of steps currently done
    @type steps: list
    @ivar needs_build: whether the recipe needs to be build or not
                       True when all steps where successful
    @type needs_build: bool
    @ivar mtime: modification time of the recipe file, used to reset the
                 state when the recipe was modified
    @type mtime: float
    '''

    def __init__(self, steps=[], needs_build=True, mtime=time.time()):
        self.steps = steps
        self.needs_build = needs_build
        self.mtime = mtime

    def touch(self):
        ''' Touches the recipe updating its modification time '''
        self.mtime = time.time()

    def __repr__(self):
        return "Steps: %r Needs Build: %r" % (self.steps, self.needs_build)


class CookBook (object):
    '''
    Stores a list of recipes and their build status saving it's state to a
    cache file

    @ivar recipes: dictionary with L{cerbero.recipe.Recipe} availables
    @type recipes: dict
    @ivar recipes: dictionary with the L{cerbero.cookbook.RecipeStatus}
    @type recipes: dict
    '''

    recipes = {}  # recipe_name -> recipe
    status = {}    # recipe_name -> RecipeStatus

    _mtimes = {}

    def __init__(self, config, load=True):
        self.set_config(config)

        if not load:
            return

        if not os.path.exists(config.recipes_dir):
            raise FatalError(_("Recipes dir %s not found") %
                             config.recipes_dir)
        self.update()

    def set_config(self, config):
        '''
        Set the configuration used

        @param config: configuration used
        @type config: L{cerbero.config.Config}
        '''
        self._config = config

    def get_config(self):
        '''
        Gets the configuration used

        @return: current configuration
        @rtype: L{cerbero.config.Config}
        '''
        return self._config

    def set_status(self, status):
        '''
        Sets the recipes status

        @param status: the recipes status
        @rtype: dict
        '''
        self.status = status

    def update(self):
        '''
        Reloads the recipes list adn updates the cookbook
        '''
        self._load_recipes()
        self.save()

    def get_recipes_list(self):
        '''
        Gets the list of recipes

        @return: list of recipes
        @rtype: list
        '''
        recipes = self.recipes.values()
        recipes.sort(key=lambda x: x.name)
        return recipes

    def add_recipe(self, recipe):
        '''
        Adds a new recipe to the cookbook

        @param recipe: the recipe to add
        @type  recipe: L{cerbero.build.cookbook.Recipe}
        '''
        self.recipes[recipe.name] = recipe

    def get_recipe(self, name):
        '''
        Gets a recipe from its name

        @param name: name of the recipe
        @type name: str
        '''
        if name not in self.recipes:
            return None
        return self.recipes[name]

    def update_step_status(self, recipe_name, step):
        '''
        Updates the status of a recipe's step

        @param recipe_name: name of the recipe
        @type recipe: str
        @param step: name of the step
        @type step: str
        '''
        status = self._recipe_status(recipe_name)
        status.steps.append(step)
        status.touch()
        self.status[recipe_name] = status
        self.save()

    def update_build_status(self, recipe_name, needs_build):
        '''
        Updates the recipe's build status

        @param recipe_name: name of the recipe
        @type recipe_name: str
        @param needs_build: wheter it's already built or not
        @type needs_build: str
        '''
        status = self._recipe_status(recipe_name)
        status.needs_build = needs_build
        status.touch()
        self.status[recipe_name] = status
        self.save()

    def step_done(self, recipe_name, step):
        '''
        Marks a step as done

        @param recipe_name: name of the recipe
        @type recipe_name: str
        @param step: name of the step
        @type step: bool
        '''
        return step in self._recipe_status(recipe_name).steps

    def recipe_needs_build(self, recipe_name):
        '''
        Whether a recipe needs to be build or not

        @param recipe_name: name of the recipe
        @type recipe_name: str
        @return: True if the recipe needs to be build
        @rtype: bool
        '''
        return self._recipe_status(recipe_name).needs_build

    def list_recipe_deps(self, recipe_name):
        '''
        List the dependencies that needs to be built in the correct build
        order for a recipe

        @param recipe_name: name of the recipe
        @type recipe_name: str
        @return: list of L{cerbero.recipe.Recipe}
        @rtype: list
        '''
        recipe = self.get_recipe(recipe_name)
        if not recipe:
            raise FatalError(_('Recipe %s not found') % recipe_name)
        return self._find_deps(recipe)

    @staticmethod
    def cache_file(config):
        if config.cache_file is not None:
            return os.path.join(CONFIG_DIR, config.cache_file)
        else:
            return COOKBOOK_FILE

    @staticmethod
    def load(config):
        status = {}
        try:
            with open(CookBook.cache_file(config), 'rb') as f:
                status = pickle.load(f)
        except Exception:
            m.warning(_("Could not recover status"))
        c = CookBook(config)
        c.set_status(status)
        return c

    def save(self):
        try:
            if not os.path.exists(CONFIG_DIR):
                os.mkdir(CONFIG_DIR)
            with open(CookBook.cache_file(self.get_config()), 'wb') as f:
                pickle.dump(self.status, f)
        except IOError, ex:
            m.warning(_("Could not cache the CookBook: %s"), ex)


    def _find_deps(self, recipe, state={}, ordered=[]):
        if state.get(recipe, 'clean') == 'processed':
            return
        if state.get(recipe, 'clean') == 'in-progress':
            raise FatalError(_("Dependency Cycle"))
        state[recipe] = 'in-progress'
        for recipe_name in recipe.list_deps():
            recipedep = self.get_recipe(recipe_name)
            if recipedep == None:
                raise FatalError(_("Recipe %s has a unknown dependency %s"
                                 % (recipe.name, recipe_name)))
            self._find_deps(recipedep, state, ordered)
        state[recipe] = 'processed'
        ordered.append(recipe)
        return ordered

    def _recipe_status(self, recipe_name):
        if recipe_name not in self.status:
            self.status[recipe_name] = RecipeStatus(steps=[])
        return self.status[recipe_name]

    def _load_recipes(self):
        self.recipes = {}
        for f in os.listdir(self._config.recipes_dir):
            filepath = os.path.join(self._config.recipes_dir, f)
            recipe = self._load_recipe_from_file(filepath)
            if recipe is None:
                m.warning(_("Could not found a valid recipe in %s") %
                                f)
                continue
            elif recipe.name is None:
                m.warning(_("The recipe in file %s doesn't contain a "
                                  "name") % f)
                continue
            self.recipes[recipe.name] = recipe

            # Check for updates in the recipe file to reset the status
            rmtime = os.path.getmtime(filepath)
            if recipe.name in self.status:
                if rmtime > self.status[recipe.name].mtime:
                    self.status[recipe.name].touch()
                    self.status[recipe.name] = RecipeStatus()

    def _load_recipe_from_file(self, filepath):
        mod_name, file_ext = os.path.splitext(os.path.split(filepath)[-1])
        try:
            d = {'Platform': Platform, 'Architecture': Architecture,
                 'BuildType': BuildType, 'SourceType': SourceType,
                 'Distro': Distro, 'DistroVersion': DistroVersion,
                 'recipe': crecipe, 'os': os}
            execfile(filepath, d)
            r = d['Recipe'](self._config)
            r.prepare()
            return r
        except Exception, ex:
            import traceback
            traceback.print_exc()
            m.warning("Error loading recipe %s" % ex)
        return None