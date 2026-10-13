"""Fabrique ``sikax.png`` et ``sikax.ico`` à partir de ``resources/icons/sikax.svg``.

    python outils/generer_icone.py

Le fichier .ico contient les tailles 16 à 256 pixels attendues par Windows
(les petites en bitmap 32 bits, la plus grande en PNG), ce qui donne une
icône nette dans l'explorateur, la barre des tâches et le titre des fenêtres.
"""

import struct
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QRectF, Qt  # noqa: E402
from PySide6.QtGui import QGuiApplication, QImage, QPainter  # noqa: E402
from PySide6.QtSvg import QSvgRenderer  # noqa: E402

TAILLES = (16, 20, 24, 32, 40, 48, 64, 128, 256)


def rendre(rendu: QSvgRenderer, taille: int) -> QImage:
    image = QImage(taille, taille, QImage.Format_ARGB32)
    image.fill(Qt.transparent)
    peintre = QPainter(image)
    peintre.setRenderHint(QPainter.Antialiasing)
    peintre.setRenderHint(QPainter.SmoothPixmapTransform)
    rendu.render(peintre, QRectF(0, 0, taille, taille))
    peintre.end()
    return image


def en_png(image: QImage) -> bytes:
    donnees = QByteArray()
    tampon = QBuffer(donnees)
    tampon.open(QIODevice.WriteOnly)
    image.save(tampon, "PNG")
    tampon.close()
    return bytes(donnees)


def en_bitmap(image: QImage) -> bytes:
    """Image au format DIB des fichiers .ico : BGRA de bas en haut, suivie du masque."""
    taille = image.width()
    entete = struct.pack("<IiiHHIIiiII", 40, taille, 2 * taille, 1, 32, 0, 0, 0, 0, 0, 0)
    lignes = []
    for y in range(taille - 1, -1, -1):
        ligne = bytearray()
        for x in range(taille):
            pixel = image.pixel(x, y)
            ligne += struct.pack("<BBBB", pixel & 0xFF, (pixel >> 8) & 0xFF, (pixel >> 16) & 0xFF, (pixel >> 24) & 0xFF)
        lignes.append(bytes(ligne))
    largeur_masque = ((taille + 31) // 32) * 4
    masque = bytes(largeur_masque) * taille
    return entete + b"".join(lignes) + masque


def ecrire_ico(chemin: Path, images) -> None:
    blocs = [en_png(i) if i.width() >= 256 else en_bitmap(i) for i in images]
    entete = struct.pack("<HHH", 0, 1, len(images))
    position = 6 + 16 * len(images)
    repertoire = b""
    for image, bloc in zip(images, blocs):
        cote = image.width() if image.width() < 256 else 0
        repertoire += struct.pack("<BBBBHHII", cote, cote, 0, 0, 1, 32, len(bloc), position)
        position += len(bloc)
    chemin.write_bytes(entete + repertoire + b"".join(blocs))


def main() -> None:
    application = QGuiApplication.instance() or QGuiApplication(sys.argv)  # noqa: F841
    dossier = RACINE / "resources" / "icons"
    rendu = QSvgRenderer(str(dossier / "sikax.svg"))
    if not rendu.isValid():
        raise SystemExit("sikax.svg est illisible")
    rendre(rendu, 256).save(str(dossier / "sikax.png"), "PNG")
    ecrire_ico(dossier / "sikax.ico", [rendre(rendu, t) for t in TAILLES])
    print("sikax.png et sikax.ico écrits dans", dossier.relative_to(RACINE))


if __name__ == "__main__":
    main()
