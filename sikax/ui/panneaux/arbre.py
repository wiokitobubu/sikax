"""Arbre du modèle : solides et points, liaisons, actions mécaniques, moteurs."""

from __future__ import annotations

from typing import Dict, Optional

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

from ...i18n import tr, traducteur
from ..document import Document, Ref
from ..icones import icone
from ..theme import theme

ROLE_REF = Qt.UserRole + 1


class PanneauArbre(QWidget):
    menu_demande = Signal(object, QPoint)

    def __init__(self, document: Document, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.doc = document
        self._elements: Dict[Ref, QTreeWidgetItem] = {}
        self._silence = False

        self.arbre = QTreeWidget()
        self.arbre.setHeaderHidden(True)
        self.arbre.setIndentation(16)
        self.arbre.setContextMenuPolicy(Qt.CustomContextMenu)
        self.arbre.setUniformRowHeights(True)
        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(4, 4, 4, 4)
        disposition.addWidget(self.arbre)

        self.arbre.currentItemChanged.connect(self._sur_selection)
        self.arbre.customContextMenuRequested.connect(self._sur_menu)
        document.modele_change.connect(self.reconstruire)
        document.selection_change.connect(self._suivre_selection)
        traducteur.abonner(self.reconstruire)
        theme.change.connect(self._sur_theme)  # méthode liée : déconnectée d'office à la destruction
        self.reconstruire()

    def _sur_theme(self, _nom: str) -> None:
        self.reconstruire()

    def _groupe(self, cle: str, pictogramme: str, nombre: int) -> QTreeWidgetItem:
        element = QTreeWidgetItem(self.arbre, [f"{tr(cle)}  ({nombre})"])
        element.setIcon(0, icone(pictogramme, "texte_secondaire", 16))
        element.setFlags(Qt.ItemIsEnabled)
        element.setExpanded(True)
        police = element.font(0)
        police.setBold(True)
        element.setFont(0, police)
        return element

    def _feuille(self, parent: QTreeWidgetItem, texte: str, pictogramme: str, ref: Ref, inactif: bool = False) -> QTreeWidgetItem:
        element = QTreeWidgetItem(parent, [texte])
        element.setIcon(0, icone(pictogramme, "texte_inactif" if inactif else "texte", 16))
        element.setData(0, ROLE_REF, ref)
        if inactif:
            element.setForeground(0, theme.couleur("texte_inactif"))
        self._elements[ref] = element
        return element

    def reconstruire(self) -> None:
        m = self.doc.mecanisme
        deplies = {ref for ref, element in self._elements.items() if element.isExpanded()}
        self._silence = True
        self.arbre.clear()
        self._elements = {}

        solides = self._groupe("arbre.solides", "solide", len(m.solides))
        for solide in m.solides.values():
            ref = Ref("solide", solide.id)
            element = self._feuille(solides, solide.nom, "bati" if solide.bati else "solide", ref)
            for point in solide.points.values():
                self._feuille(element, point.nom, "point", Ref("point", solide.id, point.id))
            element.setExpanded(ref in deplies)

        liaisons = self._groupe("arbre.liaisons", "pivot", len(m.liaisons))
        for liaison in m.liaisons.values():
            a = m.solides[liaison.solide_a].nom if liaison.solide_a in m.solides else "?"
            b = m.solides[liaison.solide_b].nom if liaison.solide_b in m.solides else "?"
            element = self._feuille(liaisons, liaison.nom, liaison.type, Ref("liaison", liaison.id))
            element.setToolTip(0, f"{tr('liaison.type.' + liaison.type)} : {a} – {b}")

        actions = self._groupe("arbre.actions", "force", len(m.actions))
        for action in m.actions.values():
            self._feuille(actions, action.nom, action.type, Ref("action", action.id), not action.actif)

        moteurs = self._groupe("arbre.moteurs", "moteur", len(m.moteurs))
        for moteur in m.moteurs.values():
            liaison = m.liaisons.get(moteur.liaison)
            texte = f"{moteur.nom}  →  {liaison.nom}" if liaison is not None else moteur.nom
            self._feuille(moteurs, texte, "moteur", Ref("moteur", moteur.id), not moteur.actif)

        if m.fond is not None:
            element = QTreeWidgetItem(self.arbre, [tr("arbre.fond")])
            element.setIcon(0, icone("photo", "texte_inactif" if not m.fond.visible else "texte", 16))
            element.setData(0, ROLE_REF, Ref("fond", "fond"))
            element.setToolTip(0, m.fond.nom)
            self._elements[Ref("fond", "fond")] = element

        self._silence = False
        self._suivre_selection()

    def _suivre_selection(self) -> None:
        self._silence = True
        element = self._elements.get(self.doc.selection) if self.doc.selection is not None else None
        self.arbre.setCurrentItem(element)
        if element is not None:
            self.arbre.scrollToItem(element)
        self._silence = False

    def _sur_selection(self, courant: Optional[QTreeWidgetItem], _precedent) -> None:
        if self._silence:
            return
        ref = courant.data(0, ROLE_REF) if courant is not None else None
        if ref is not None:
            self.doc.selectionner(ref)

    def _sur_menu(self, position: QPoint) -> None:
        element = self.arbre.itemAt(position)
        ref = element.data(0, ROLE_REF) if element is not None else None
        if ref is not None:
            self.doc.selectionner(ref)
        self.menu_demande.emit(ref, self.arbre.viewport().mapToGlobal(position))
