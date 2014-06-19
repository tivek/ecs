"""Entity and System Managers."""

import six

from ecs.exceptions import (
    NonexistentComponentTypeForEntity, DuplicateSystemTypeError,
    SystemAlreadyAddedToManagerError)


class EntityManager(object):
    """Provide database-like access to components based on an entity key."""
    def __init__(self):
        self._database = {}
        self._entity_mask = {}
        self._next_guid = 0
        self._next_component_bit = 1
        self._component_bits = {}

    @property
    def database(self):
        """Get this manager's database. Direct modification is not
        permitted.

        :return: the database
        :rtype: :class:`dict`
        """
        return self._database

    def create_entity(self):
        """Return a new entity instance with the current lowest GUID value.
        Initializes the entity's component lookup bitmask to 0. Does not
        make entries in the component database referencing it.

        :return: the new entity
        :rtype: :class:`ecs.models.Entity`
        """
        entity = self._next_guid
        self._next_guid += 1
        self._entity_mask[entity] = 0
        return entity

    def add_component(self, entity, component_instance):
        """Add a component to the database and associate it with the given
        entity.

        :param entity: entity to associate
        :type entity: :class:`ecs.models.Entity`
        :param component_instance: component to add to the entity
        :type component_instance: :class:`ecs.models.Component`
        """
        component_type = type(component_instance)
        if component_type not in self._database:
            self._database[component_type] = {}
        if component_type not in self._component_bits:
            self._component_bits[component_type] = self._next_component_bit
            self._next_component_bit <<= 1

        self._entity_mask[entity] = self._entity_mask[entity] | \
            self._component_bits[component_type]
        self._database[component_type][entity] = component_instance

    def remove_component(self, entity, component_type):
        """Remove the component of ``component_type`` associated with
        entity from the database. Doesn't do any kind of data-teardown. It is
        up to the system calling this code to do that. In the future, a
        callback system may be used to implement type-specific destructors.

        :param entity: entity to associate
        :type entity: :class:`ecs.models.Entity`
        :param component_type: component type to remove from the entity
        :type component_type: :class:`type` which is :class:`Component`
            subclass
        """
        try:
            del self._database[component_type][entity]
            if not self._database[component_type]:
                del self._database[component_type]
            self._entity_mask[entity] = self._entity_mask[entity] & \
                (~self._component_bits[component_type])
        except KeyError:
            pass

    def pairs_for_type(self, component_type):
        """Return an iterator over ``(entity, component_instance)`` tuples for
        all entities in the database possessing a component of
        ``component_type``. Return an empty iterator if there are no components
        of this type in the database. It should be used in a loop like this,
        where ``Renderable`` is a component type:

        .. code-block:: python

            for entity, renderable_component in \
entity_manager.pairs_for_type(Renderable):
                pass # do something

        :param component_type: a type of created component
        :type component_type: :class:`type` which is :class:`Component`
            subclass
        :return: iterator on ``(entity, component_instance)`` tuples
        :rtype: :class:`iter` on
            (:class:`ecs.models.Entity`, :class:`ecs.models.Component`)
        """
        try:
            return six.iteritems(self._database[component_type])
        except KeyError:
            return six.iteritems({})

    def pairs_for_types(self, *component_types):
        """Return an iterator over ``(entity, (component_instances...))``
        tuples for all entities in the database possessing components of all of
        ``component_types``. Return an empty iterator if there are no entities
        containing these types of components in the database. It should be
        used in a loop like this, where ``Renderable`` and ``PlayerControl``
        are component types:

        .. code-block:: python

            for entity, (renderable_component, control_component) in \
entity_manager.pairs_for_types(Renderable, PlayerControl):
                pass # do something

        :param component_types: types of components required in an entity
        :type component_types: :class:`type` which is :class:`Component`
            subclass
        :return: iterator on ``(entity, (component_instance...))`` tuples
        :rtype: :class:`iter` on
            (:class:`ecs.models.Entity`,
            :tuple:(:class:`ecs.models.Component`,...))
        """
        try:
            mask = self._build_mask(*component_types)
            shortest = min((self._database[ct] for ct in component_types),
                           key=len)
            return ((entity, tuple(self._database[ct][entity]
                                   for ct in component_types))
                    for entity in shortest
                    if self._entity_mask[entity] & mask == mask)
        except KeyError:
            return []

    def _build_mask(self, *component_types):
        """Build a componennt bitmask which represents entities containing
        all the ``component_types``.

        :param component_types: component types to be included in the bitmas
        :type component_types: :class:`type` which is :class:`Component`
            subclass
        :return: integer bitmask
        :rtype: int
        """
        mask = 0
        for component_type in component_types:
            mask |= self._component_bits[component_type]
        return mask

    def component_for_entity(self, entity, component_type):
        """Return the instance of ``component_type`` for the entity from the
        database.

        :param entity: associated entity
        :type entity: :class:`ecs.models.Entity`
        :param component_type: a type of created component
        :type component_type: :class:`type` which is :class:`Component`
            subclass
        :return: component instance
        :rtype: :class:`ecs.models.Component`
        :raises: :exc:`NonexistentComponentTypeForEntity` when
            ``component_type`` does not exist on the given entity
        """
        try:
            return self._database[component_type][entity]
        except KeyError:
            raise NonexistentComponentTypeForEntity(
                entity, component_type)

    def components_for_entity(self, entity, *component_types):
        """Multi component analog to
        :meth:`component_for_entity`, works
        the same but accepts more than one component type.
        Return the instances of ``component_types`` for the entity in a tuple
        from the database.

        :param entity: associated entity
        :type entity: :class:`ecs.models.Entity`
        :param component_types: one or more types of created components
        :type component_types: :class:`type` which is :class:`Component`
            subclass
        :return: component instances as tuple
        :rtype: :class:`tuple` of :class:`ecs.models.Component`
        :raises: :exc:`NonexistentComponentTypeForEntity` for the first
            type from ``component_types`` that does not exist on the given
            entity
        """
        try:
            return tuple(self._database[component][entity]
                            for component in component_types)
        except KeyError:
            for component in component_types:
                # since we iterate over types in a generator expression
                # we have to do it here again to find the component that
                # caused the KeyError
                if not component in self._database or \
                   not entity in self._database[component]:
                    raise NonexistentComponentTypeForEntity(
                        entity, component) from None

    def remove_entity(self, entity):
        """Remove all components from the database that are associated with
        the entity, with the side-effect that the entity is also no longer
        in the database.

        :param entity: entity to remove
        :type entity: :class:`ecs.models.Entity`
        """
        # For Python 2, don't use iterkeys(), otherwise we will get a
        # RuntimeError about mutating the length of the dictionary at runtime.
        # For Python 3, we can't even use keys(), because that is a view object
        # that acts like iterkeys(). We therefore make a copy using list() to
        # avoid modifying the iterator.
        for comp_type in list(self._database.keys()):
            try:
                del self._database[comp_type][entity]
                if not self._database[comp_type]:
                    del self._database[comp_type]
            except KeyError:
                pass
        try:
            del self._entity_mask[entity]
        except KeyError:
            pass


class SystemManager(object):
    """A container and manager for :class:`ecs.models.System` objects."""
    def __init__(self, entity_manager):
        """:param entity_manager: this manager's entity manager
        :type entity_manager: :class:`SystemManager`
        """
        self._systems = []
        self._system_types = {}
        self._entity_manager = entity_manager

    # Allow getting the list of systems but not directly setting it.
    @property
    def systems(self):
        """Get this manager's list of systems.

        :return: system list
        :rtype: :class:`list` of :class:`ecs.models.System`
        """
        return self._systems

    def add_system(self, system_instance, priority=0):
        """Add a :class:`ecs.models.System` instance to the manager.

        :param system_instance: instance of a system
        :param priority: non-negative integer (default: 0)
        :type system_instance: :class:`ecs.models.System`
        :type priority: :class:`int`
        :raises: :class:`ecs.exceptions.DuplicateSystemTypeError` when the
            system type is already present in this manager
        :raises: :class:`ecs.exceptions.SystemAlreadyAddedToManagerError` when
            the system already belongs to a system manager
        """
        system_type = type(system_instance)
        if system_type in self._system_types:
            raise DuplicateSystemTypeError(system_type)
        if system_instance.system_manager is not None:
            raise SystemAlreadyAddedToManagerError(
                system_instance, self, system_instance.system_manager)
        system_instance.entity_manager = self._entity_manager
        system_instance.system_manager = self
        self._system_types[system_type] = system_instance
        self._systems.append(system_instance)

        system_instance.priority = priority
        self._systems.sort(key=lambda x: x.priority)

    def remove_system(self, system_type):
        """Tell the manager to no longer run the system of this type.

        :param system_type: type of system to remove
        :type system_type: :class:`type`
        """
        system = self._system_types[system_type]
        system.entity_manager = None
        system.system_manager = None
        self._systems.remove(system)
        del self._system_types[system_type]

    def update(self, dt):
        """Run each system's ``update()`` method for this frame. The systems
        are run in the order in which they were added.

        :param dt: delta time, or elapsed time for this frame
        :type dt: :class:`float`
        """
        # Iterating over a list of systems instead of values in a dictionary is
        # noticeably faster. We maintain a list in addition to a dictionary
        # specifically for this purpose.
        #
        # Though initially we had the entity manager being passed through to
        # each update() method, this turns out to cause quite a large
        # performance penalty. So now it is just set on each system.
        for system in self._systems:
            system.update(dt)
