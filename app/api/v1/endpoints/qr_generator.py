from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.responses import StreamingResponse
import qrcode
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
from fastapi import Depends
from app.core.deps import get_current_user
from app.database.models.user import User

router = APIRouter()

@router.post("/generate")
async def generate_qr(
    data: str = Query(...),
    current_user: User = Depends(get_current_user)
):
    """
    Generates a single QR code image for the given data.
    """
    if not data:
        raise HTTPException(status_code=400, detail="Data cannot be empty")
    
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    
    # Save to buffer
    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    
    return StreamingResponse(buf, media_type="image/png")

@router.post("/chess-set")
async def generate_chess_set(current_user: User = Depends(get_current_user)):
    """
    Generates a sheet (grid) of 32 QR codes for a chess set:
    - 2 Kings, 2 Queens, 4 Rooks, 4 Bishops, 4 Knights, 16 Pawns
    - Barcode format: CHESS_[SIDE]_[PIECE]_[ID]
    """
    # Define the pieces
    pieces = [
        ("WHITE", "KING", 1), ("WHITE", "QUEEN", 1), ("WHITE", "ROOK", 2), 
        ("WHITE", "BISHOP", 2), ("WHITE", "KNIGHT", 2), ("WHITE", "PAWN", 8),
        ("BLACK", "KING", 1), ("BLACK", "QUEEN", 1), ("BLACK", "ROOK", 2), 
        ("BLACK", "BISHOP", 2), ("BLACK", "KNIGHT", 2), ("BLACK", "PAWN", 8)
    ]
    
    barcodes = []
    for side, piece, count in pieces:
        for i in range(1, count + 1):
            barcodes.append(f"CHESS_{side}_{piece}_{i}")
    
    # Create a grid image (e.g., 4x8)
    cols = 4
    rows = 8
    cell_size = 300
    margin = 20
    
    canvas_w = cols * cell_size
    canvas_h = rows * cell_size
    
    sheet = Image.new('RGB', (canvas_w, canvas_h), color='white')
    draw = ImageDraw.Draw(sheet)
    
    for idx, barcode in enumerate(barcodes):
        if idx >= cols * rows: break
        
        c = idx % cols
        r = idx // cols
        
        # Generate QR
        qr = qrcode.QRCode(box_size=6)
        qr.add_data(barcode)
        qr.make(fit=True)
        qr_img = qr.make_image(fill_color="black", back_color="white").convert('RGB')
        qr_img = qr_img.resize((cell_size - 60, cell_size - 60))
        
        # Paste QR
        x = c * cell_size + 30
        y = r * cell_size + 20
        sheet.paste(qr_img, (x, y))
        
        # Add label text
        # (Assuming default font is available, or use a basic one)
        draw.text((x + 10, y + cell_size - 40), barcode, fill="black")
    
    # Save to buffer
    buf = BytesIO()
    sheet.save(buf, format="PNG")
    buf.seek(0)
    
    return StreamingResponse(buf, media_type="image/png")
