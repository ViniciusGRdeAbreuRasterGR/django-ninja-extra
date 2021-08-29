import inspect
from functools import wraps
from typing import TYPE_CHECKING
from ninja import Query
from ninja import params
from ninja.signature import is_async
from ninja.types import TCallable

if TYPE_CHECKING:
    from .route import Route
    from ninja_extra.controllers.base import APIController

__all__ = ["RouteFunction", 'PaginatedRouteFunction', 'RetrieveObjectRouteFunction']


class RouteFunction:
    def __call__(self, *args, **kwargs):
        pass

    def __init__(self, route_definition: "Route", api_func):
        self.route_definition = route_definition
        self.api_func = api_func

    @classmethod
    def get_required_api_func_signature(cls, api_func: TCallable):
        skip_parameters = ['context', 'self', 'request']
        sig_inspect = inspect.signature(api_func)
        sig_parameter = [
            parameter for parameter in sig_inspect.parameters.values()
            if parameter.name not in skip_parameters
        ]
        return sig_inspect, sig_parameter

    def _resolve_api_func_signature_(self, api_func, context_func):
        # Override signature
        sig_inspect, sig_parameter = self.get_required_api_func_signature(api_func)
        sig_replaced = sig_inspect.replace(parameters=sig_parameter)
        context_func.__signature__ = sig_replaced
        return context_func

    # def __set_name__(self, owner: "APIController", name):
    #     self.route_definition.controller = owner
    #     self.route_definition.queryset = self.route_definition.queryset or owner.queryset
    #     self.route_definition.permissions = self.route_definition.permissions or owner.permission_classes
    #
    #     setattr(owner, name, self.api_func)
    #     add_from_route = getattr(owner, 'add_from_route', None)
    #     if add_from_route:
    #         add_from_route(self.route_definition)

    @classmethod
    def from_route(cls, api_func: TCallable, route_definition: "Route"):
        route_function = cls(route_definition=route_definition, api_func=api_func)
        if is_async(api_func):
            return route_function.convert_async_api_func_to_context_view(api_func=api_func), route_function
        return route_function.convert_api_func_to_context_view(api_func=api_func), route_function

    def convert_api_func_to_context_view(self, api_func: TCallable):
        @wraps(api_func)
        def context_func(request, *args, **kwargs):
            controller_instance = self.get_owner_instance(request, *args, **self.filter_registered_kwargs(kwargs))
            controller_instance.check_permissions()
            return self.run_view_func(controller_instance=controller_instance)

        return self._resolve_api_func_signature_(api_func, context_func)

    def convert_async_api_func_to_context_view(
            self, api_func: TCallable
    ):
        @wraps(api_func)
        async def context_func(request, *args, **kwargs):
            controller_instance = self.get_owner_instance(request, *args, **self.filter_registered_kwargs(kwargs))
            controller_instance.check_permissions()
            return await self.async_run_view_func(controller_instance=controller_instance)

        return self._resolve_api_func_signature_(api_func, context_func)

    def run_view_func(self, controller_instance: "APIController"):
        return controller_instance.run_view_func(self.api_func)

    async def async_run_view_func(self, controller_instance: "APIController"):
        return await controller_instance.async_run_view_func(self.api_func)

    def get_owner_instance(self, request, *args, **kwargs):
        return self.route_definition.create_view_func_instance(request, *args, **kwargs)

    def filter_registered_kwargs(self, kwargs):
        return kwargs


class RetrieveObjectRouteFunction(RouteFunction):
    def run_view_func(self, controller_instance: "APIController"):
        return controller_instance.run_object_view_func(self.api_func)

    async def async_run_view_func(self, controller_instance: "APIController"):
        return await controller_instance.async_run_object_view_func(self.api_func)


class PaginatedRouteFunction(RouteFunction):
    registered_filter = False

    def _resolve_api_func_signature_(
            self, api_func, context_func
    ):
        route_definition: "Route" = self.route_definition
        # Override signature for Ninja API documentation purposes

        sig_inspect, required_func_signature = self.get_required_api_func_signature(api_func)
        # check if API func has any query params before injecting one.
        # Ninja api functions only allows on Query parameter
        has_query_param = any((type(param.default) == type(params.Query)
                               for param in required_func_signature))
        # if extract signatures are pass to the api_function, we ignore the
        if not has_query_param:
            query_params = inspect.Parameter(
                name='filters',
                kind=inspect.Parameter.KEYWORD_ONLY,
                default=Query(...),
                annotation=route_definition.resolve_paginated_request_schema(),
            )
            required_func_signature.append(query_params)
            self.registered_filter = True
        sig_replaced = sig_inspect.replace(parameters=required_func_signature)
        context_func.__signature__ = sig_replaced
        return context_func

    def run_view_func(self, controller_instance: "APIController"):
        return controller_instance.run_list_view_func(self.api_func)

    async def async_run_view_func(self, controller_instance: "APIController"):
        return await controller_instance.async_run_list_view_func(self.api_func)

    def filter_registered_kwargs(self, kwargs):
        if self.registered_filter:
            kwargs.pop('filters')
        return kwargs