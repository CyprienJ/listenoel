
# 🎁 nosCadeaux

[![Quality Gate Status](https://sonarcloud.io/api/project_badges/measure?project=CyprienJ_noscadeaux&metric=alert_status)](https://sonarcloud.io/summary/new_code?id=CyprienJ_noscadeaux)
[![Security Rating](https://sonarcloud.io/api/project_badges/measure?project=CyprienJ_noscadeaux&metric=security_rating)](https://sonarcloud.io/summary/new_code?id=CyprienJ_noscadeaux)
[![Maintainability Rating](https://sonarcloud.io/api/project_badges/measure?project=CyprienJ_noscadeaux&metric=sqale_rating)](https://sonarcloud.io/summary/new_code?id=CyprienJ_noscadeaux)

## 🏠 Accès
🌐 Site web : [noscadeaux.fr](https://noscadeaux.fr)

---

Une application web Django moderne pour organiser et partager des listes de cadeaux entre proches. Créez des groupes, partagez vos souhaits et coordonnez-vous facilement pour les occasions spéciales !

---
## Fonctionnalités

- 👥 **Création de groupes** : pour partager ces cadeaux dans différents cercles sociaux (familles, amis, ...)
- 🎯 **Gestion de listes de souhaits** : Ajoutez, modifiez et organisez des idées cadeaux
- 🔗 **Partage par invitation** : Invitez facilement des membres via des liens sécurisés
- 📧 **Notifications email** : Recevez une notification quand un membre choisis ajoute quelque chose à ça liste
- 🌍 **Interface multilingue** : Support français et anglais
- 🔐 **Authentification sécurisée** : Système complet de gestion d'utilisateurs
- 🦊 **Ajout rapide Firefox** : Extraction d'un produit depuis une boutique avec validation avant ajout

Le prototype de l'extension Firefox et ses instructions de développement se trouvent dans
[`firefox-extension/`](firefox-extension/).

---
## 🛠 Stack Technique

- **Framework** : Django 6.0 avec Python 3.12+
- **Frontend** : HTML5, CSS3, JavaScript
- **Base de données** : PostgreSQL (production), SQLite (développement)
- **Gestionnaire de paquets** : UV
- **Déploiement** : Docker + Nginx + Gunicorn
- **CI/CD** : GitHub Actions

## Notes de développement

- À chaque ajout ou modification de texte visible par les utilisateurs, penser à mettre à jour les traductions Django (`locale/*/LC_MESSAGES/django.po`) puis recompiler les messages.

### Versionnement

La version applicative suit le format `X.Y.Z` et sa source de vérité est le champ
`project.version` de `pyproject.toml`. Avant d'ouvrir une pull request, l'incrémenter
selon la nature du changement :

```bash
uv version --bump patch  # correction
uv version --bump minor  # fonctionnalité rétrocompatible
uv version --bump major  # changement incompatible
```

Le check CI `Version incremented` échoue si la version d'une pull request n'est pas
strictement supérieure à celle de la branche cible. Ce check doit être déclaré
obligatoire dans le ruleset GitHub de `main`. Lors du build, le workflow injecte
automatiquement cette version et le hash complet du commit dans l'unique image
Docker `latest`.

### Notes de version

Les nouveautés visibles par les utilisateurs sont définies dans
`gifts/release_notes/X.Y.Z.toml`. Le nom du fichier et son champ `version`
doivent correspondre à la version concernée. Une traduction française est
obligatoire et une traduction anglaise peut être ajoutée :

```toml
version = "1.2.0"
date = 2026-08-18

[fr]
title = "Titre de la nouveauté"
content = "Description affichée dans la modale et le changelog."

[en]
title = "Update title"
content = "Description shown in the modal and changelog."
```

La CI valide automatiquement ces fichiers. La commande peut aussi être lancée
localement avec `uv run python manage.py validate_release_notes`.

### Signalement public des bugs

Le formulaire `/bug-report/` crée directement une issue GitHub et ne stocke aucun
signalement dans la base de données. Configurez le service avec :

- `BUG_REPORT_REPOSITORY` : dépôt public au format `propriétaire/dépôt` ;
- `BUG_REPORT_TOKEN` : jeton finement limité à ce dépôt avec `Issues: write` ;
- `BUG_REPORT_LABELS` : labels séparés par des virgules (facultatif).

Le jeton doit rester exclusivement côté serveur. Le dépôt doit être public pour que
les visiteurs sans compte GitHub puissent consulter le ticket créé. Le fichier
`.env.example` documente les variables sans contenir de secret. La version et la
révision publiées dans le ticket proviennent automatiquement de l’image déployée.

## Licence

Ce projet est distribué sous licence GNU Affero General Public License v3.0 ou ultérieure (`AGPL-3.0-or-later`). Consultez le fichier [LICENSE](LICENSE) pour le texte complet de la licence.
