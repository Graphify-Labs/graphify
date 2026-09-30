namespace Inventory.Service

open System
open System.Collections.Generic

type Sku = Sku of string

type StockLevel = { Sku: Sku; OnHand: int; Reserved: int }

type StockError =
    | UnknownSku of Sku
    | Insufficient of requested: int * available: int

type IStockStore =
    abstract member Find: Sku -> StockLevel option
    abstract member Save: StockLevel -> unit

module Stock =
    let available level = level.OnHand - level.Reserved

    let reserve qty level =
        if available level >= qty then
            Ok { level with Reserved = level.Reserved + qty }
        else
            Error (Insufficient (qty, available level))

    let rec drain qty levels =
        match levels with
        | [] -> []
        | level :: rest -> takeFrom qty level :: drain qty rest

    and takeFrom qty level =
        { level with OnHand = max 0 (level.OnHand - qty) }

type StoreBase() =
    abstract member Name: string
    default this.Name = "base"

type MemoryStore() =
    inherit StoreBase()
    let items = Dictionary<Sku, StockLevel>()

    override this.Name = "memory"

    member this.Count = items.Count

    interface IStockStore with
        member this.Find sku =
            match items.TryGetValue sku with
            | true, level -> Some level
            | _ -> None

        member this.Save level = items.[level.Sku] <- level

module Api =
    let reserveOrFail (store: IStockStore) sku qty =
        match store.Find sku with
        | None -> Error (UnknownSku sku)
        | Some level ->
            level
            |> Stock.reserve qty
            |> Result.map (fun updated -> store.Save updated; updated)

    let summary levels =
        levels
        |> List.map Stock.available
        |> List.sum
