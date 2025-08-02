"""
Component Registry

Registry for managing and organizing showcase components.
"""

from typing import Dict, List, Optional, Type, Any
from dataclasses import dataclass


@dataclass
class ComponentEntry:
    """Registry entry for a showcase component."""
    name: str
    category: str
    description: str
    component_class: Type[Any]
    example_code: str = ""
    tags: List[str] = None
    
    def __post_init__(self):
        if self.tags is None:
            self.tags = []


class ComponentRegistry:
    """
    Registry for managing showcase components.
    
    This class maintains a collection of components that can be showcased,
    organized by category and searchable by various criteria.
    """
    
    def __init__(self):
        """Initialize the component registry."""
        self._components: Dict[str, ComponentEntry] = {}
        self._categories: Dict[str, List[str]] = {}
    
    def register(self, name: str, category: str, description: str, 
                 component_class: Type[Any], example_code: str = "", 
                 tags: List[str] = None) -> None:
        """
        Register a component in the showcase.
        
        Args:
            name: Unique name for the component
            category: Category for organizing components
            description: Brief description of the component
            component_class: The actual component class
            example_code: Example usage code
            tags: Optional tags for searching/filtering
        """
        # Create component entry
        entry = ComponentEntry(
            name=name,
            category=category,
            description=description,
            component_class=component_class,
            example_code=example_code,
            tags=tags or []
        )
        
        # Store in registry
        self._components[name] = entry
        
        # Add to category
        if category not in self._categories:
            self._categories[category] = []
        self._categories[category].append(name)
    
    def get_component(self, name: str) -> Optional[ComponentEntry]:
        """
        Get a registered component by name.
        
        Args:
            name: Name of the component to retrieve
            
        Returns:
            Component entry if found, None otherwise
        """
        return self._components.get(name)
    
    def get_components_by_category(self, category: str) -> List[ComponentEntry]:
        """
        Get all components in a specific category.
        
        Args:
            category: Category name
            
        Returns:
            List of component entries in the category
        """
        names = self._categories.get(category, [])
        return [self._components[name] for name in names]
    
    def get_all_categories(self) -> List[str]:
        """
        Get all registered categories.
        
        Returns:
            List of category names
        """
        return list(self._categories.keys())
    
    def search(self, query: str) -> List[ComponentEntry]:
        """
        Search for components by name, description, or tags.
        
        Args:
            query: Search query string
            
        Returns:
            List of matching component entries
        """
        query = query.lower()
        matches = []
        
        for entry in self._components.values():
            # Check name, description, and tags
            if (query in entry.name.lower() or 
                query in entry.description.lower() or
                any(query in tag.lower() for tag in entry.tags)):
                matches.append(entry)
        
        return matches


# Global component registry instance
_component_registry = ComponentRegistry()


def showcase_component(name: str, category: str, description: str, 
                      example_code: str = "", tags: List[str] = None):
    """
    Decorator for registering components in the showcase.
    
    Args:
        name: Unique name for the component
        category: Category for organizing components
        description: Brief description of the component
        example_code: Example usage code
        tags: Optional tags for searching/filtering
        
    Example:
        @showcase_component(
            name="ImageViewer",
            category="Image Display",
            description="Widget for displaying images with zoom and pan",
            example_code='''
from src.pk_py_lib.gui.widgets import ImageViewer

viewer = ImageViewer()
viewer.load_image("path/to/image.jpg")
viewer.show()
''',
            tags=["image", "viewer", "display"]
        )
        class ImageViewer(QLabel):
            # Implementation here
            pass
    """
    def decorator(cls):
        _component_registry.register(
            name=name,
            category=category,
            description=description,
            component_class=cls,
            example_code=example_code,
            tags=tags
        )
        return cls
    return decorator


# Export public API
__all__ = [
    "ComponentRegistry",
    "ComponentEntry",
    "showcase_component",
    "_component_registry"
]