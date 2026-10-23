Create Procedure CG_ItemsFacturaARemitir
@IDFactura int
as
Select * from CG_ItemsFacturas Where Tipo = 0 AND SubTipo < 3 AND Identificador = @IDFactura 

(1 rows affected)
