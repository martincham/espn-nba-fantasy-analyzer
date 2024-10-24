import library.schedule as schedule
import library.config as config


# I want to calculate overrall ratings (and then specific stat ratings)

    # 1. load league  and free agents for each year
    # 2. create a dictionary/data structure, populate like:
        # Lebron James { Overall : {
        # 2023: 123,
        # 2024: 234,
        # 2025: 187,
        # 2026: 146,
        # },
        # PTS: {2023: 123, 2024: 234, 2025: 187, 2026: 146},
        # BLK: {2023: 123, 2024: 234, 2025: 187, 2026: 146},
        # STL: {2023: 123, 2024: 234, 2025: 187, 2026: 146},
        # AST: {2023: 123, 2024: 234, 2025: 187, 2026: 146},
        # REB: {2023: 123, 2024: 234, 2025: 187, 2026: 146},
        # 3PM: {2023: 123, 2024: 234, 2025: 187, 2026: 146},
        # }
        #
    # 3. Create Pandas DataFrame from dictionary, one per stat
    # 4. Rows will be players, columns will be years
    # 5. Export to Google Sheet
