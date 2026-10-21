"""TGE RDN - ceny energii dla Home Assistant.

Czysty Python (biblioteka standardowa). Jedna biblioteka pobiera i parsuje
strone TGE, drugi policzy plan ladowania, trzeci pisze pliki JSON, ktore
czytaja sensory `command_line` w Home Assistant.

Publiczne API:
    fetch_day()    - pobiera ceny na jedna dobe
    build_plan()   - liczy okno najtanszych godzin
    build_payload()- buduje strukture JSON dla HA
"""

__version__ = '2.0.0'
__all__ = ['__version__']
