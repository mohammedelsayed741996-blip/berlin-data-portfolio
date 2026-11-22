// Power Query (M): load one table of the star schema straight from GitHub.
// Create one query per table and change TableName: fact_po_line, dim_supplier, dim_material, dim_category, dim_plant, dim_month.
let
    BaseUrl = "https://raw.githubusercontent.com/mohammedelsayed741996-blip/berlin-data-portfolio/main/energy-grid-technology/procurement-spend-analytics/data/model/",
    TableName = "fact_po_line",
    Source = Csv.Document(Web.Contents(BaseUrl & TableName & ".csv"), [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    // dates and numbers are written in invariant format, so parse with en-US regardless of the user's locale
    Typed = if TableName = "fact_po_line" then
        Table.TransformColumnTypes(Promoted, {
            {"order_date", type date}, {"month", type date}, {"due_date", type date}, {"receipt_date", type date},
            {"quantity", type number}, {"unit_price_eur", type number}, {"spend_eur", Currency.Type}, {"days_late", Int64.Type},
            {"is_return", type logical}, {"on_contract", type logical}, {"maverick", type logical}, {"defect", type logical},
            {"category_was_blank", type logical}, {"price_corrected", type logical}, {"on_time", type number}}, "en-US")
      else if TableName = "dim_month" then Table.TransformColumnTypes(Promoted, {{"month", type date}, {"year", Int64.Type}}, "en-US")
      else Promoted
in
    Typed
