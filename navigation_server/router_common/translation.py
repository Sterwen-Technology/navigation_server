#-------------------------------------------------------------------------------
# Name:        translation
# Purpose:     Multilingual support for the navigation server
#
# Author:      Vibe Code
#
# Created:     2025
# Copyright:   (c) Sterwen Technology 2021-2025
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import logging
import os
import yaml
from typing import Dict, Optional

_logger = logging.getLogger("ShipDataServer." + __name__)


class TranslationManager:
    """
    Manages multilingual translations for the navigation server.
    Supports loading translations from YAML files and switching languages at runtime.
    """
    
    # Default language
    DEFAULT_LANGUAGE = "en"
    
    # Supported languages
    SUPPORTED_LANGUAGES = ["en", "fr"]
    
    def __init__(self):
        self._translations: Dict[str, Dict[str, str]] = {}
        self._current_language: str = self.DEFAULT_LANGUAGE
        self._translations_loaded: bool = False
        self._translations_dir: Optional[str] = None
    
    def initialize(self, language: Optional[str] = None, translations_dir: Optional[str] = None):
        """
        Initialize the translation system.
        
        Args:
            language: The language to use (e.g., 'en', 'fr')
            translations_dir: Directory containing translation YAML files
        """
        if language is not None and language in self.SUPPORTED_LANGUAGES:
            self._current_language = language
        else:
            _logger.warning(f"Unsupported language '{language}', defaulting to '{self.DEFAULT_LANGUAGE}'")
            self._current_language = self.DEFAULT_LANGUAGE
        
        self._translations_dir = translations_dir
        
        # Load translations for the current language
        self._load_translations()
    
    def _load_translations(self):
        """Load translation files for all supported languages."""
        if self._translations_loaded:
            return
        
        # Try to find translations directory
        search_dirs = []
        if self._translations_dir:
            search_dirs.append(self._translations_dir)
        
        # Add default locations
        from .global_variables import MessageServerGlobals
        if MessageServerGlobals.home_dir:
            search_dirs.append(os.path.join(MessageServerGlobals.home_dir, "translations"))
        
        # Also check in the navigation_server directory
        search_dirs.append(os.path.join(os.path.dirname(__file__), "..", "..", "translations"))
        
        for lang in self.SUPPORTED_LANGUAGES:
            self._translations[lang] = {}
            
            for base_dir in search_dirs:
                if not os.path.isdir(base_dir):
                    continue
                    
                lang_file = os.path.join(base_dir, f"{lang}.yml")
                if os.path.exists(lang_file):
                    try:
                        with open(lang_file, 'r', encoding='utf-8') as f:
                            lang_translations = yaml.safe_load(f)
                            if lang_translations and isinstance(lang_translations, dict):
                                self._translations[lang].update(lang_translations)
                                _logger.info(f"Loaded {len(lang_translations)} translations for {lang} from {lang_file}")
                    except (IOError, yaml.YAMLError) as e:
                        _logger.error(f"Error loading translations for {lang} from {lang_file}: {e}")
                else:
                    _logger.debug(f"Translation file not found: {lang_file}")
        
        self._translations_loaded = True
        _logger.info(f"Translation system initialized with language: {self._current_language}")
    
    def set_language(self, language: str) -> bool:
        """
        Set the current language.
        
        Args:
            language: Language code to set (e.g., 'en', 'fr')
            
        Returns:
            True if language was changed successfully, False otherwise
        """
        if language not in self.SUPPORTED_LANGUAGES:
            _logger.warning(f"Language '{language}' not supported. Supported languages: {self.SUPPORTED_LANGUAGES}")
            return False
        
        if language == self._current_language:
            return True
        
        old_language = self._current_language
        self._current_language = language
        _logger.info(f"Language changed from {old_language} to {language}")
        return True
    
    def get_language(self) -> str:
        """Get the current language."""
        return self._current_language
    
    def _get_nested_value(self, d: dict, key_path: str):
        """
        Get a value from a nested dictionary using dot notation.
        
        Args:
            d: The dictionary to search
            key_path: The key path (e.g., 'server.starting', 'error.invalid_config')
            
        Returns:
            The value if found, None otherwise
        """
        keys = key_path.split('.')
        value = d
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return None
        return value

    def translate(self, key: str, default: Optional[str] = None, **kwargs) -> str:
        """
        Translate a key to the current language.
        
        Args:
            key: The translation key (e.g., 'server.starting', 'error.invalid_config')
            default: Default value if key not found
            **kwargs: Variables for string formatting
            
        Returns:
            Translated string or default if not found
        """
        # Try to get translation for current language
        lang_translations = self._translations.get(self._current_language, {})
        translated = self._get_nested_value(lang_translations, key)
        
        if translated is not None:
            if kwargs:
                try:
                    return translated.format(**kwargs)
                except (KeyError, ValueError) as e:
                    _logger.warning(f"Error formatting translation for key '{key}': {e}")
                    return translated
            return translated
        
        # Fallback to default language if available
        if self._current_language != self.DEFAULT_LANGUAGE:
            default_translations = self._translations.get(self.DEFAULT_LANGUAGE, {})
            translated = self._get_nested_value(default_translations, key)
            if translated is not None:
                if kwargs:
                    try:
                        return translated.format(**kwargs)
                    except (KeyError, ValueError):
                        return translated
                return translated
        
        # Return default or the key itself
        if default is not None:
            if kwargs:
                try:
                    return default.format(**kwargs)
                except (KeyError, ValueError):
                    return default
            return default
        
        _logger.debug(f"Translation key '{key}' not found")
        return key
    
    def t(self, key: str, default: Optional[str] = None, **kwargs) -> str:
        """
        Convenience method for translate().
        
        Args:
            key: The translation key
            default: Default value if key not found
            **kwargs: Variables for string formatting
            
        Returns:
            Translated string
        """
        return self.translate(key, default, **kwargs)
    
    def add_translation(self, language: str, key: str, value: str):
        """
        Add or override a translation at runtime.
        
        Args:
            language: Language code
            key: Translation key
            value: Translation value
        """
        if language not in self._translations:
            self._translations[language] = {}
        self._translations[language][key] = value
        _logger.debug(f"Added translation for {language}.{key} = {value}")
    
    def get_supported_languages(self) -> list:
        """Get list of supported languages."""
        return self.SUPPORTED_LANGUAGES.copy()


# Global translation manager instance
translation_manager = TranslationManager()


def init_translation(language: Optional[str] = None, translations_dir: Optional[str] = None):
    """
    Initialize the global translation system.
    
    Args:
        language: Language to use
        translations_dir: Directory with translation files
    """
    translation_manager.initialize(language, translations_dir)


def set_language(language: str) -> bool:
    """
    Set the global translation language.
    
    Args:
        language: Language code to set
        
    Returns:
        True if successful, False otherwise
    """
    return translation_manager.set_language(language)


def get_language() -> str:
    """Get the current global language."""
    return translation_manager.get_language()


def translate(key: str, default: Optional[str] = None, **kwargs) -> str:
    """
    Translate a key using the global translation manager.
    
    Args:
        key: Translation key
        default: Default value if not found
        **kwargs: Variables for string formatting
        
    Returns:
        Translated string
    """
    return translation_manager.translate(key, default, **kwargs)


def t(key: str, default: Optional[str] = None, **kwargs) -> str:
    """
    Convenience function for translate().
    
    Args:
        key: Translation key
        default: Default value if not found
        **kwargs: Variables for string formatting
        
    Returns:
        Translated string
    """
    return translate(key, default, **kwargs)
