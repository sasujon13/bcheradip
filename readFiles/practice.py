
    def display_institutes_units_years(self, obj):
        # Retrieve all related institutes, units, and years
        institutes = obj.institutes.all()
        institute_units = obj.instituteUnits.all()
        years = obj.years.all()

        # Combine institute, unit, and year data to recreate the original "year_institute" pairs
        year_institute_pairs = []

        for institute in institutes:
            related_units = institute_units.filter(instituteUnits__institutes=institute).distinct()
            related_years = years.filter(years__institutes=institute).distinct()
            if related_years.exists():
                for related_year in related_years:
                    if related_units.exists():
                        for related_unit in related_units:
                            pair = f"{institute.institute_code}-{related_unit.unit} '{related_year.year_code}"
                    else:
                        pair = f"{institute.institute_code} '{related_year.year_code}"
            else:
                pair = f"{institute.institute_code}"
            year_institute_pairs.append(pair)

        return ", ".join(year_institute_pairs) if year_institute_pairs else "NA"

    display_institutes_units_years.short_description = 'Exam'