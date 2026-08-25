

"""
Configuration Module
====================
Centralized configuration management for the entire application.

This module contains all configuration classes and constants organized by
domain. Uses dataclasses for type-safe configuration with validation.

Structure:
    - Environment variables loaded from .env
    - API clients configuration (Tavily, OpenRouter, Firecrawl)
    - Domain filtering (trusted/unreliable domains)
    - Content cleaning configuration
    - Document chunking configuration
"""

import os
from dataclasses import dataclass, field
from typing import List, Set, Optional, Dict, Any
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()





# ============================================================================
# SECTION 1: API CLIENTS CONFIGURATION
# ============================================================================

@dataclass
class TavilyConfig:
    """
    Configuration for Tavily search API client.
    Tavily provides search capabilities optimized for AI applications.
    """

    api_key: str = os.getenv("TAVILY_API_KEY", "")

    search_depth: str =os.getenv("TAVILY_SEARCH_DEPTH","")

    max_results: int = int(os.getenv("TAVILY_MAX_RESULTS", "5"))
    

   


@dataclass
class FirecrawlConfig:
    """
    Configuration for Firecrawl web scraping API client.
    
    Firecrawl is optional - if API key is not provided, client will be disabled.
    """
    api_key: str = os.getenv("FIRECRAWL_API_KEY", "")
    
    timeout: int = int(os.getenv("FIRECRAWL_TIMEOUT", "30"))
    
    max_pages: int = int(os.getenv("FIRECRAWL_MAX_PAGES", "10"))


    @property
    def is_enabled(self) -> bool:
        """Check if Firecrawl is configured and available."""
        return bool(self.api_key)
    
    def validate(self) -> None:
        """Validate Firecrawl configuration (only if enabled)."""
        if self.is_enabled:
            if self.timeout <= 0:
                raise ValueError(f"timeout must be positive, got {self.timeout}")
            if self.max_pages <= 0:
                raise ValueError(f"max_pages must be positive, got {self.max_pages}")

    



@dataclass
class OpenRouterConfig:
    """
    Configuration for OpenRouter LLM API client.
    OpenRouter provides access to multiple LLM models through a single API.
    """

    api_key: str = os.getenv("OPENROUTER_API_KEY", "")

    base_url: str = "https://openrouter.ai/api/v1"

    
    default_model: str = "openai/gpt-oss-120b"
        
    
    default_temperature: float = float(os.getenv("DEFAULT_TEMPERATURE", "0.3"))
    
    default_max_tokens:int=int(os.getenv("DEFAULT_MAX_TOKENS", "2048"))
    
    
    def validate(self) -> None:
        """Validate OpenRouter configuration."""
        if not self.api_key:
            raise ValueError(
                "OPENROUTER_API_KEY is required. Set it in .env file or environment."
            )
        if not 0.0 <= self.default_temperature <= 1.0:
            raise ValueError(
                f"Temperature must be between 0.0 and 1.0, "
                f"got {self.default_temperature}"
            )
        if self.default_max_tokens <= 0:
            raise ValueError(
                f"max_tokens must be positive, got {self.default_max_tokens}"
            )







# ============================================================================
# SECTION 2: DSPY CONFIGURATION
# ============================================================================

@dataclass
class DSPyConfig:
    """
    Configuration for DSPy framework.   
    DSPy is a framework for programming LLMs with structured prompts.
    """

    model: str = os.getenv("DSPY_MODEL", "openai/gpt-oss-120b")
    
    temperature: float = float(os.getenv("DSPY_TEMPERATURE", "0.3"))
    
    max_tokens: int = int(os.getenv("DSPY_MAX_TOKENS", "2048"))
    
    
    def validate(self) -> None:
        """Validate DSPy configuration."""
        if not self.model:
            raise ValueError("DSPY_MODEL is required")
        if not 0.0 <= self.temperature <= 1.0:
            raise ValueError(
                f"Temperature must be between 0.0 and 1.0, "
                f"got {self.temperature}"
            )







# ============================================================================
# SECTION 3: DOMAINS CONFIGURATION
# ============================================================================

@dataclass
class DomainsConfig:
    """
    Configuration for domain filtering in web search.
    
    Defines which domains are considered reliable/unreliable for content
    extraction and search results.
    """
    
    # Unreliable domains (social media, user-generated content, etc.)
    unreliable: Set[str] = field(default_factory=lambda:{
        # Social Media
        "youtube.com", "youtu.be", "facebook.com", "twitter.com", "x.com",
        "instagram.com", "tiktok.com", "linkedin.com", "pinterest.com",
        "tumblr.com", "snapchat.com", "whatsapp.com", "telegram.org",
        
        # User-Generated Content
        "reddit.com", "quora.com", "medium.com", "blogspot.com", 
        "wordpress.com", "wix.com", "weebly.com", "squarespace.com",
        "hubpages.com", "wikihow.com",
        
        # Document Sharing
        "scribd.com", "slideshare.net", "issuu.com",
        
        # LinkedIn Pulse (blog posts)
        "linkedin.com/pulse",
    })
    
    # Trusted domains (official, academic, institutional, etc.)
    trusted: Set[str] = field(default_factory=lambda:{
        # French Government & Official
        "gouv.fr", "legifrance.gouv.fr", "insee.fr", 
        "economie.gouv.fr", "banque-france.fr",
        "statistiques.developpement-durable.gouv.fr",
        
        # International Organizations
        "europa.eu", "european-union.europa.eu",
        "worldbank.org", "imf.org", "oecd.org", "who.int", "unesco.org",
        
        # Academic & Research
        "cairn.info", "erudit.org", "jstor.org",
        "sciencedirect.com", "springer.com", "ieee.org", "acm.org",
        "arxiv.org", "researchgate.net", "scholar.google.com",
        
        # Universities
        "harvard.edu", "stanford.edu", "mit.edu", 
        "ox.ac.uk", "cambridge.org",
        
        # Business & Tech
        "g2.com", "capterra.com", "trustpilot.com", "glassdoor.fr",
        
        # News & Media
        "lesechos.fr", "lemonde.fr", "lefigaro.fr",
        "ft.com", "wsj.com", "bloomberg.com",
        "forbes.com", "businessinsider.com",
        "techcrunch.com", "wired.com",
    })







# ============================================================================
# SECTION 4: CONTENT CLEANER CONFIGURATION
# ============================================================================

@dataclass
class CleanerConfig:
    """
    Configuration for content cleaning and noise removal.
    
    Handles cleaning of scraped content by removing common noise patterns
    like cookie notices, social media links, and tracking parameters.
    """
    
    # Minimum line length to keep (shorter lines are likely noise)
    min_line_length: int = int(os.getenv("CLEANER_MIN_LINE_LENGTH", "25"))
    
    
    # Directory names for input/output
    output_dir_name:str=os.getenv("CLEANER_OUTPUT_DIR", "clean_markdown")
    
    input_dir_name: str = os.getenv("CLEANER_INPUT_DIR", "raw_markdown")
    
    
    # Patterns de bruit à supprimer
    noise_patterns: List[str] =field(default_factory=lambda:[
        # Cookie & Privacy
        r"cookie",
        r"accept cookies",
        r"privacy policy",
        r"terms of service",
        
        # Calls to action
        r"subscribe",
        r"sign in",
        r"log in",
        r"login",
        r"register",
        r"contact us",
        
        # Advertising
        r"advertisement",
        r"all rights reserved",
        
        # Social media
        r"share on facebook",
        r"share on twitter",
        r"follow us",
        r"instagram",
        r"linkedin",
        r"youtube",
        r"facebook",
        r"twitter",
        r"tiktok",
        
        # Navigation
        r"back to top",
        r"skip to content",
        r"menu",
        r"navigation",
        r"skip to main content",
        
        # Legal
        r"copyright",
        r"author",
        
        # Report specific
        r"report code",
        r"table of contents",
        r"download sample",
        r"request free sample",
        r"buy now",
        r"get free sample",
        r"related reports",
        r"market report",
        r"report overview",
        r"updated on",
        
        # Market research specific
        r"maximize market research",
        
        # Application promotions
        r"discover the app",
        r"download the app",
        r"available on",
        r"app store",
        r"google play",
    ])
    
    # Patterns de partage social et applications
    share_patterns: List[str] =field(default_factory=lambda: [
        # French
        r"Partager par mail",
        r"Partager par email",
        r"Découvrez l'application",
        r"Découvrez l'app",
        r"Téléchargez l'application",
        r"Suivez-nous sur",
        r"Rejoignez-nous sur",
        
        # English
        r"Share by email",
        r"Share via email",
        r"Download the app",
        r"Follow us on",
        r"Join us on",
        
        # General
        r"Disponible sur",
        r"Available on",
    ])
    
    # URL encoding patterns and tracking parameters
    url_encoding_patterns: List[str] =field(default_factory=lambda: [
        r'%[0-9A-Fa-f]{2}',        # URL encoding
        r'%0D%0A',                 # Encoded line breaks
        r'utm_[a-z_]+=',           # UTM tracking parameters
        r'[?&]ref=[^&\s]+',        # Referral parameters
        r'[?&]source=[^&\s]+',     # Source parameters
    ])
    
    def get_all_patterns(self) -> List[str]:
        """Get all cleaning patterns combined."""
        return self.noise_patterns + self.share_patterns + self.url_encoding_patterns





# ============================================================================
# SECTION 5: CHUNKER CONFIGURATION
# ============================================================================

@dataclass
class ChunkerConfig:
    """
    Configuration for document chunking.
    
    Controls how documents are split into chunks for processing,
    with overlap to maintain context.
    """
    
    # Size parameters (in characters/tokens)
    max_chunk_size: int =  int(os.getenv("CHUNKER_MAX_SIZE", "1000"))
    
    min_chunk_size: int = int(os.getenv("CHUNKER_MIN_SIZE", "100"))
    
    overlap_size: int = int(os.getenv("CHUNKER_OVERLAP", "100"))
    
    
    # Quality parameters
    min_quality_score: float = float(os.getenv("CHUNKER_MIN_QUALITY", "0.3"))
    
    min_tokens: int =int(os.getenv("CHUNKER_MIN_TOKENS", "20"))
    
    max_tokens: int = int(os.getenv("CHUNKER_MAX_TOKENS", "2000"))
    
    
    # Behavior flags
    preserve_headers: bool = os.getenv("CHUNKER_PRESERVE_HEADERS", "true").lower() == "true"
    
    preserve_intro: bool = os.getenv("CHUNKER_PRESERVE_INTRO", "true").lower() == "true"
    
    remove_empty_chunks: bool = os.getenv("CHUNKER_REMOVE_EMPTY", "true").lower() == "true"
    


















































# from dataclasses import dataclass, field
# from typing import List
# import os
# from dotenv import load_dotenv

# load_dotenv()

# # ===========================================================================
# #CLIENT CONFIGURATION
# # ===========================================================================

# CLIENT_CONFIG = {
    
# # Tavily Configuration
# # -----------------
# "TAVILY_API_KEY" :os.getenv("TAVILY_API_KEY"),
# "TAVILY_SEARCH_DEPTH":"andvanced",

# # OpenRouter Configuration
# # --------------------
# "OPENROUTER_API_KEY" : os.getenv("OPENROUTER_API_KEY"),
# "OPENROUTER_BASE_URL":"https://openrouter.ai/api/v1",
# "DEFAULT_MODEL":"openai/gpt-oss-120b",
# "DEFAULT_TEMPERATURE":  0.3,
# "DEFAULT_MAX_TOKENS": 2048,


# # FireCrawl Configuration
# # --------------------
# "FIRECRAWL_API_KEY" : os.getenv("FIRECRAWL_API_KEY"),
# "FIRECRAWL_TIMEOUT": int(os.getenv("FIRECRAWL_TIMEOUT", "30")),

# # DSPy Configuration
# # --------------------
# "DSPY_MODEL": "openai/gpt-4-32k",

# }



# # =====================================================================
# #  DOMAINS CONFIGURATION FOR WEB SEARCH 
# # =====================================================================

# # Constants
# # ---------------------------------
# from dataclasses import dataclass, field
# from typing import List


# UNRELIABLE_DOMAINS = {
#     "youtube.com","youtu.be","facebook.com","twitter.com","instagram.com","tiktok.com",
#     "linkedin.com/pulse","reddit.com","quora.com","medium.com","blogspot.com","wordpress.com",
#     "wix.com","weebly.com","squarespace.com", "hubpages.com","wikihow.com","scribd.com",
#     "slideshare.net","issuu.com","pinterest.com","tumblr.com","snapchat.com","whatsapp.com","telegram.org",
# }


# TRUSTED_DOMAINS = {
#     "gouv.fr","legifrance.gouv.fr","insee.fr","economie.gouv.fr","banque-france.fr",
#     "europa.eu","european-union.europa.eu","worldbank.org","imf.org","oecd.org","who.int",
#     "unesco.org","statistiques.developpement-durable.gouv.fr","cairn.info","erudit.org","jstor.org",
#     "sciencedirect.com","springer.com","ieee.org","acm.org","arxiv.org","researchgate.net",
#     "scholar.google.com","harvard.edu","stanford.edu","mit.edu","ox.ac.uk","cambridge.org","g2.com",
#     "capterra.com","trustpilot.com","glassdoor.fr","lesechos.fr","lemonde.fr","lefigaro.fr",
#     "ft.com","wsj.com","bloomberg.com","forbes.com","businessinsider.com","techcrunch.com","wired.com",
# }





# # ============================================================================
# # CONTENT CLEANER CONFIGURATION
# # ============================================================================


# @dataclass
# class CleanerConfig:
#     """Configuration du nettoyeur de contenu"""
#     min_line_length: int = 25
#     output_dir_name: str = "clean_markdown"
#     input_dir_name: str = "raw_markdown"
    
#     # Patterns de bruit à supprimer
#     noise_patterns: List[str] = field(default_factory=lambda: [
#         r"cookie",
#         r"accept cookies",
#         r"privacy policy",
#         r"terms of service",
#         r"subscribe",
#         r"sign in",
#         r"log in",
#         r"login",
#         r"register",
#         r"advertisement",
#         r"all rights reserved",
#         r"share on facebook",
#         r"share on twitter",
#         r"follow us",
#         r"newsletter",
#         r"back to top",
#         r"skip to content",
#         r"menu",
#         r"navigation",
#         r"copyright",
#         r"instagram",
#         r"linkedin",
#         r"youtube",
#         r"facebook",
#         r"twitter",
#         r"tiktok",
#         r"author",
#         r"report code",
#         r"updated on",
#         r"skip to main content",
#         r"maximize market research",
#         r"table of contents",
#         r"download sample",
#         r"request free sample",
#         r"buy now",
#         r"get free sample",
#         r"contact us",
#         r"related reports",
#         r"market report",
#         r"report overview",
#     ])
    
#     # Patterns de partage social et applications
#     share_patterns: List[str] = field(default_factory=lambda: [
#         r"Partager par mail",
#         r"Partager par email",
#         r"Share by email",
#         r"Share via email",
#         r"Découvrez l'application",
#         r"Découvrez l'app",
#         r"Téléchargez l'application",
#         r"Download the app",
#         r"Disponible sur",
#         r"Available on",
#         r"App Store",
#         r"Google Play",
#         r"Suivez-nous sur",
#         r"Follow us on",
#         r"Rejoignez-nous sur",
#         r"Join us on",
#     ])
    
#     # Patterns d'URL encodées et de paramètres de tracking
#     url_encoding_patterns: List[str] = field(default_factory=lambda: [
#         r'%[0-9A-Fa-f]{2}',  # Encodage URL
#         r'%0D%0A',           # Retours à la ligne encodés
#         r'utm_[a-z_]+=',     # Paramètres UTM
#         r'[?&]ref=[^&\s]+',  # Paramètres de référence
#         r'[?&]source=[^&\s]+', # Paramètres de source
#     ])







# # ============================================================================
# # CONFIGURATION DU CHUNKER 
# # ============================================================================


# CHUNKR_CONFIG = {
#     "max_chunk_size": 1000,
#     "min_chunk_size": 100,
#     "overlap_size": 100,
#     "preserve_headers": True,
#     "preserve_intro": True,
#     "remove_empty_chunks": True,
#     "min_quality_score": 0.3,
#     "min_tokens": 20,
#     "max_tokens": 2000

# }








