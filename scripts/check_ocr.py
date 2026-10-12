"""Local OCR smoke check; never downloads or touches the document library."""
from PIL import Image, ImageDraw, ImageFont
from yastreb.ocr import check_available, recognize


def main():
    check_available()
    with Image.new('RGB', (1600, 350), 'white') as image:
        ImageDraw.Draw(image).text((50, 110), 'Installation report 12 days',
                                   font=ImageFont.load_default(size=60), fill='black')
        text = recognize(image)
    if '12' not in text or 'report' not in text.lower():
        raise RuntimeError('OCR self-test failed. Run install.cmd again.')
    print('OCR VERIFIED: offline image recognition; rus/eng languages available.')


if __name__ == '__main__':
    main()
