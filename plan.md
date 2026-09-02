# Plan d'implémentation — Refonte de la création de compte

Référence : [issue GitHub #133 — Revoir la création de compte](https://github.com/CyprienJ/noscadeaux/issues/133)

## 1. Objectif

Mettre en place un parcours d'arrivée progressif qui permet à un nouvel utilisateur de :

1. créer son compte avec son adresse e-mail et son mot de passe ;
2. valider son adresse e-mail ;
3. compléter son profil en comprenant l'utilité des informations demandées ;
4. rejoindre un groupe existant ou en créer un ;
5. après la création d'un groupe, inviter d'autres personnes ou ajouter des personnes sans compte.

Le résultat attendu est un parcours guidé, reprenable et compatible avec les liens d'invitation, sans supprimer les possibilités actuelles de gérer plusieurs groupes, listes et événements.

## 2. Stratégie de livraison

Les lots 1 à 5 sont des étapes de développement d'un même chantier. **Aucune mise en production ne sera effectuée entre le lot 1 et le lot 5.**

Conséquences :

- un lot intermédiaire peut laisser un écran inaccessible, une redirection provisoire ou un parcours partiellement fonctionnel si le lot suivant le complète ;
- les lots n'ont pas besoin d'être activables séparément en production ;
- aucun feature flag n'est requis uniquement pour maintenir la compatibilité entre deux lots ;
- les tests ciblés du lot doivent rester utiles, mais la suite complète peut temporairement échouer si l'échec est identifié, documenté et corrigé dans un lot suivant ;
- la branche ne devient candidate à la mise en production qu'après le lot 5 et la validation de tous les critères finaux ;
- les migrations doivent néanmoins rester reproductibles dans l'ordre et être testées, avant livraison, depuis l'état de la base actuellement en production.

Chaque lot possède donc deux niveaux de contrôle :

- **critères de sortie du lot** : suffisamment de garanties pour poursuivre le développement ;
- **critères d'acceptation finaux** : comportement obligatoire dans la version livrée après le lot 5.

## 3. Terminologie produit

Pour éviter la confusion entre le compte utilisateur et l'espace partagé :

- **compte** : identité permettant à une personne de se connecter ;
- **profil** : pseudo, anniversaire et photo associés au compte ;
- **groupe** : espace privé réunissant plusieurs personnes et leurs listes ;
- **personne sans compte** : personne représentée dans un groupe, dont la liste est gérée par les membres du groupe ;
- **invitation** : lien ou message permettant de rejoindre un groupe.

Le terme « faux compte » ou « fausse personne » ne doit pas apparaître dans l'interface.

## 4. Parcours cible

### 4.1 Arrivée sans invitation

```text
Inscription
  → validation de l'e-mail
  → configuration du profil
  → créer ou rejoindre un groupe
  → accueil du groupe ou tableau de bord
```

L'étape groupe propose également « Plus tard ». Cette sortie évite de bloquer un utilisateur souhaitant uniquement utiliser une liste événementielle ou découvrir l'application. Son utilisation devra être mesurable afin de vérifier si elle est réellement nécessaire.

### 4.2 Arrivée depuis une invitation

```text
Lien d'invitation
  → aperçu limité du groupe
  → connexion ou inscription
  → validation de l'e-mail si nécessaire
  → configuration du profil si nécessaire
  → confirmation d'adhésion
  → groupe invité
```

Le contexte de l'invitation ne doit être perdu à aucune étape.

### 4.3 Utilisateur existant

- Un utilisateur connecté et déjà configuré arrive directement sur l'aperçu du groupe.
- Un utilisateur connecté mais non vérifié est renvoyé vers la validation de son e-mail, puis revient à l'invitation.
- Un utilisateur déjà membre ne rejoint pas le groupe une seconde fois et reçoit un message explicite.
- Un lien invalide, expiré ou révoqué ne révèle aucune donnée privée sur le groupe.

## 5. Principes structurants et attendus futurs

### 5.1 Onboarding versionné et reprenable

Le modèle `User` devra stocker un état persistant, par exemple :

- `onboarding_version`, entier initialisé à `0` ;
- `onboarding_completed_at`, date facultative.

La version cible du chantier sera centralisée dans une constante applicative. Un service ou une fonction unique déterminera la prochaine étape à partir de l'état de l'utilisateur, au lieu de disperser la logique dans les vues et le middleware.

Ce choix doit permettre ultérieurement :

- d'ajouter une étape sans renvoyer arbitrairement tous les utilisateurs dans l'ancien parcours ;
- de proposer un complément de profil aux anciens comptes ;
- de reprendre le parcours après une déconnexion ou un changement d'appareil ;
- de mesurer l'abandon par étape sans conserver de données personnelles supplémentaires.

### 5.2 Données de profil minimales

- Le pseudo est obligatoire à la fin de l'étape profil.
- La photo est facultative.
- L'anniversaire reste facultatif et limité au jour et au mois : l'année de naissance n'est pas nécessaire au fonctionnement actuel et ne doit pas être collectée.
- Les valeurs doivent rester modifiables ensuite depuis la page du compte.

Cette structure reste compatible avec de futurs réglages de visibilité ou de rappels sans collecter dès maintenant une date de naissance complète.

### 5.3 Invitations évolutives

Le code court saisi manuellement et le secret contenu dans un lien n'ont pas le même usage :

- le **code de groupe** reste court et saisissable ;
- le **token de lien d'invitation** doit être long, aléatoire et non devinable.

Le lien sécurisé peut être porté par un nouveau champ du groupe dans cette première version. La génération et l'envoi doivent passer par un service dédié afin qu'une future évolution vers un modèle `GroupInvitation` soit possible sans réécrire les vues.

Le modèle futur pourra supporter :

- une invitation individuelle liée à une adresse e-mail ;
- une date d'expiration ;
- la révocation d'une invitation ;
- le suivi envoyé/accepté/refusé ;
- plusieurs niveaux de permissions ;
- la limitation du nombre d'utilisations.

Ces fonctionnalités de suivi ne font pas partie du périmètre obligatoire de l'issue #133.

### 5.4 Personnes sans compte revendicables à terme

La version livrée continue d'utiliser un utilisateur technique inactif lié à un `ManagedMember`. La création doit être atomique et ne jamais produire l'un sans l'autre.

Le modèle et les services ne doivent pas empêcher une évolution permettant à une personne invitée de transformer ou revendiquer ultérieurement ce profil géré, en conservant sa liste et son historique. La revendication elle-même est hors périmètre de ce chantier.

### 5.5 Autorisations centralisées

Le comportement actuel autorise largement les membres à modifier le groupe et ses invitations. Le chantier ne doit pas introduire un système complet de rôles, mais les contrôles d'autorisation nouvellement ajoutés doivent être centralisés pour préparer des rôles futurs tels que propriétaire, administrateur et membre.

### 5.6 Sécurité et confidentialité

- Une adhésion est une mutation et doit être confirmée par une requête `POST`, jamais par un simple `GET`.
- Les URL de retour doivent être internes et validées pour empêcher les redirections ouvertes.
- L'aperçu anonyme ne montre que le nom, l'image éventuelle et un nombre de membres ; il ne montre ni noms, ni listes, ni adresses e-mail.
- L'envoi d'invitations doit être limité par utilisateur et par groupe afin d'éviter le spam.
- Les réponses ne doivent pas permettre de déterminer si une adresse possède déjà un compte.
- Les tokens ne doivent pas être journalisés en clair dans les logs applicatifs.

## 6. Lot 1 — Socle d'onboarding et création du compte

### Objectif

Créer le socle persistant du parcours et réduire le premier écran à l'identité de connexion.

### Travaux attendus

#### Modèle et migrations

- Ajouter les champs d'état d'onboarding retenus sur `User`.
- Définir une stratégie de migration des utilisateurs existants : les utilisateurs vérifiés existants sont considérés comme ayant terminé la version 1 afin de ne pas être bloqués lors de la mise en production.
- Laisser les nouveaux utilisateurs à la version `0` jusqu'à la fin du parcours.
- Centraliser la version cible de l'onboarding.

#### Formulaire d'inscription

- Remplacer le formulaire actuel par un formulaire contenant uniquement :
  - adresse e-mail ;
  - mot de passe ;
  - confirmation du mot de passe.
- Conserver la validation Turnstile existante.
- Normaliser l'adresse e-mail avant la recherche d'unicité.
- Créer temporairement l'utilisateur avec un pseudo vide jusqu'au lot 2.
- Connecter l'utilisateur après la création et envoyer l'e-mail de validation.
- Rediriger explicitement vers la page « Vérifiez votre e-mail » au lieu de compter sur une redirection indirecte du middleware.

#### Validation de l'e-mail

- Corriger l'affichage de l'adresse e-mail sur la page de confirmation.
- Conserver le renvoi de l'e-mail avec délai anti-abus côté serveur ; le délai JavaScript ne doit pas être la seule protection.
- Après validation, appeler le résolveur d'onboarding, même si l'écran profil n'est ajouté qu'au lot 2.
- Décider et documenter la durée de vie d'un compte non vérifié. Si les 30 minutes actuelles sont conservées, l'information doit être clairement affichée.

#### Résolution de la prochaine étape

- Créer une fonction unique du type `get_onboarding_next_url(user, request)`.
- Le middleware et les vues d'authentification doivent utiliser cette fonction.
- Prévoir la prise en compte d'une destination métier en attente, notamment une invitation.

### Critères de sortie du lot 1

- Une migration peut être appliquée et annulée sur une base de test.
- Un nouveau compte peut être créé avec uniquement e-mail et mot de passe.
- L'e-mail de vérification est envoyé.
- Un compte non vérifié ne peut pas accéder aux écrans privés.
- Le résolveur d'onboarding possède des tests unitaires pour les états vérifié/non vérifié et onboarding terminé/non terminé.
- Les éventuelles redirections provisoires vers un écran du lot 2 sont identifiées dans la branche.

### Préparation des critères finaux

- Étant donné un visiteur, lorsqu'il soumet une adresse valide et deux mots de passe identiques, alors son compte est créé et la page de validation est affichée.
- Étant donné une adresse déjà utilisée, le formulaire affiche une erreur sans divulguer d'information supplémentaire dans l'e-mail envoyé.
- Étant donné un compte non vérifié, toute tentative d'accès à un écran privé reprend la validation de l'e-mail.

## 7. Lot 2 — Configuration du profil

### Objectif

Recueillir les informations utiles au fonctionnement social de l'application après la validation de l'adresse e-mail.

### Travaux attendus

- Ajouter une route et un template dédiés, par exemple `/onboarding/profile/`.
- Créer un formulaire distinct du formulaire de paramètres du compte afin d'éviter de modifier l'adresse e-mail pendant l'onboarding.
- Demander :
  - pseudo, obligatoire ;
  - jour et mois d'anniversaire, facultatifs mais indissociables ;
  - photo téléversée ou preset, facultatif.
- Afficher à proximité de chaque champ :
  - pseudo : « Visible par les personnes de vos groupes » ;
  - anniversaire : « Utilisé pour les rappels ; l'année n'est pas demandée » ;
  - photo : « Aide les membres de vos groupes à vous reconnaître ».
- Permettre d'ignorer séparément l'anniversaire et la photo.
- Réutiliser les validateurs et le traitement d'image existants.
- À la soumission valide, enregistrer le profil puis demander au résolveur la prochaine étape.
- Empêcher un utilisateur non vérifié de valider cette étape.
- Permettre à un utilisateur ayant interrompu le parcours de reprendre cet écran après reconnexion.

### Critères de sortie du lot 2

- Le formulaire refuse un pseudo vide.
- Une date impossible est refusée.
- Jour et mois sont tous deux vides ou tous deux renseignés.
- Aucune année de naissance n'est demandée ni stockée.
- Une photo valide est redimensionnée selon le comportement existant.
- L'étape peut être terminée sans anniversaire et sans photo.
- Après reconnexion, un profil incomplet est redirigé vers cette étape.

### Préparation des critères finaux

- Étant donné un compte vérifié sans profil, lorsqu'il se connecte, alors il arrive sur la configuration du profil.
- Étant donné un profil valide, lorsqu'il est enregistré, alors les explications de confidentialité ont été visibles et les données restent modifiables depuis le compte.
- Étant donné un utilisateur ayant déjà terminé cette étape, lorsqu'il consulte directement son URL, alors il est redirigé vers la prochaine étape pertinente.

## 8. Lot 3 — Créer ou rejoindre un groupe

### Objectif

Terminer l'onboarding en donnant un contexte social immédiat à l'utilisateur, tout en conservant une sortie non bloquante.

### Travaux attendus

#### Écran de choix

- Ajouter une page proposant clairement :
  - « Créer un groupe » ;
  - « Rejoindre avec un code » ;
  - « Plus tard ».
- Réutiliser `GroupForm` pour la création.
- Réutiliser le mécanisme de code existant pour rejoindre un groupe.
- Marquer l'onboarding version 1 comme terminé après création, adhésion ou choix « Plus tard ».
- Rediriger une création vers la future page d'invitation du lot 4 ; une redirection provisoire est acceptable dans ce lot.

#### Conservation du contexte d'invitation

- Autoriser l'ouverture d'un lien d'invitation par un visiteur non connecté.
- Stocker une destination d'invitation validée pendant l'inscription et la validation e-mail.
- Ne jamais accepter une URL de retour externe.
- Lorsque le profil est terminé, privilégier l'invitation en attente à l'écran générique de choix.
- Gérer le cas où l'invitation devient invalide pendant le parcours, puis proposer de créer ou rejoindre un autre groupe.

#### Acceptation

- Transformer la confirmation d'adhésion en formulaire `POST` protégé par CSRF.
- Préserver l'idempotence : accepter deux fois ne crée pas deux adhésions.
- Ne terminer l'onboarding qu'après une décision explicite de l'utilisateur.

### Critères de sortie du lot 3

- Les trois sorties de l'écran de choix fonctionnent.
- Le créateur est membre du groupe qu'il vient de créer.
- Un code valide permet de rejoindre un groupe ; un code invalide affiche un message compréhensible.
- L'acceptation d'une invitation utilise `POST`.
- Un utilisateur déjà membre ne crée pas de doublon.
- Une URL de retour externe est ignorée.
- Le parcours d'invitation fonctionne au minimum dans le même navigateur ; le comportement entre appareils est testé et documenté selon la stratégie retenue.

### Préparation des critères finaux

- Étant donné un utilisateur sans invitation, lorsqu'il termine son profil, alors il peut créer, rejoindre ou remettre à plus tard.
- Étant donné un visiteur arrivé par invitation, lorsqu'il termine inscription, validation et profil, alors il retrouve le groupe initialement invité.
- Étant donné une invitation invalide, aucune information privée du groupe n'est révélée.

## 9. Lot 4 — Inviter après la création d'un groupe

### Objectif

Donner au créateur les moyens de peupler immédiatement son groupe.

### Travaux attendus

#### Écran post-création

- Ajouter une page dédiée après la création du groupe avec :
  - copie du lien ;
  - partage natif lorsque le navigateur le permet ;
  - envoi d'une ou plusieurs invitations par e-mail ;
  - accès à l'ajout de personnes sans compte, finalisé au lot 5 ;
  - bouton explicite pour terminer et ouvrir le groupe.
- L'écran doit rester accessible ultérieurement depuis la page du groupe.

#### Lien sécurisé

- Séparer le token de lien du code court saisi manuellement.
- Générer le token avec un générateur cryptographiquement sûr et une entropie suffisante.
- Conserver les codes existants lors de la migration.
- Prévoir une action de régénération qui invalide l'ancien lien.
- Ne pas afficher le token dans les messages serveur ou les logs.

#### Partage et copie

- Construire les URL côté serveur, avec le bon domaine et la bonne langue.
- Utiliser l'API Web Share si elle est disponible, avec repli vers la copie dans le presse-papiers.
- Afficher une confirmation accessible après copie ou partage.

#### Invitations par e-mail

- Créer un service d'invitation indépendant de la vue.
- Accepter plusieurs adresses avec validation et déduplication.
- Envoyer un e-mail texte et HTML traduit, contenant le nom du groupe, le nom de l'invitant et le lien sécurisé.
- Ne pas exposer les destinataires entre eux.
- Limiter la fréquence et le volume d'envoi côté serveur.
- Afficher un bilan générique des envois sans révéler quelles adresses possèdent déjà un compte.
- En cas d'échec partiel du fournisseur d'e-mail, conserver le groupe et permettre une nouvelle tentative.

### Hors périmètre du lot 4

- relance automatique ;
- carnet d'adresses ;
- suivi détaillé des ouvertures ;
- invitation avec rôle ;
- date d'expiration individuelle ;
- suppression automatique d'un groupe vide.

### Critères de sortie du lot 4

- La création d'un groupe conduit à l'écran d'invitation.
- Le lien copié ouvre le bon groupe.
- L'ancien lien ne fonctionne plus après régénération.
- Le code court continue de fonctionner indépendamment du lien.
- Un e-mail d'invitation contient un lien fonctionnel et n'expose aucun autre destinataire.
- Les limites d'envoi possèdent des tests.
- Une panne d'envoi n'annule pas la création du groupe.
- Le partage possède un repli fonctionnel sur navigateur non compatible.

### Préparation des critères finaux

- Étant donné un groupe nouvellement créé, son créateur peut inviter sans chercher l'action dans le tableau de bord.
- Étant donné plusieurs adresses valides, chacune reçoit son propre message sans connaître les autres destinataires.
- Étant donné un utilisateur dépassant la limite d'envoi, aucun nouveau message n'est envoyé et une erreur compréhensible est affichée.

## 10. Lot 5 — Personnes sans compte et consolidation finale

### Objectif

Compléter la promesse de l'issue et rendre l'ensemble du chantier livrable en production.

### Travaux attendus

#### Correction du modèle actuel

- Corriger `add_managed_member`, qui crée actuellement un `User` technique sans créer explicitement le `ManagedMember` correspondant.
- Créer dans une transaction :
  - l'utilisateur technique inactif ;
  - le `ManagedMember` associé ;
  - l'adhésion au groupe.
- Attribuer une couleur de manière déterministe à partir de la palette existante.
- En cas d'erreur, ne conserver aucun objet orphelin.
- Vérifier les règles de suppression afin que la suppression de la personne supprime ses données conformément au comportement affiché à l'utilisateur.

#### Intégration à l'onboarding de groupe

- Depuis l'écran post-création, permettre d'ajouter plusieurs personnes sans compte successivement.
- Demander uniquement le prénom ou nom d'affichage.
- Expliquer que tous les membres du groupe peuvent gérer la liste de cette personne.
- Afficher immédiatement la personne ajoutée avec un accès à sa liste.
- Autoriser à ignorer cette étape et à terminer l'onboarding.

#### Consolidation

- Supprimer les redirections et écrans provisoires laissés par les lots précédents.
- Vérifier toutes les routes directes et tous les retours après connexion/déconnexion.
- Harmoniser les textes et remplacer les usages ambigus de « compte » lorsqu'ils désignent un groupe.
- Compléter les traductions française et anglaise.
- Vérifier l'affichage mobile, clavier et lecteur d'écran des nouveaux écrans.
- Ajouter les événements de mesure strictement nécessaires au funnel, sans e-mail, pseudo ni token dans les données analytiques.
- Mettre à jour la documentation utilisateur et les notes de version.

### Critères de sortie du lot 5

- La création d'une personne sans compte produit toujours un couple cohérent `User` technique / `ManagedMember`.
- Une personne sans compte apparaît dans le groupe et sa liste est accessible.
- Son renommage met à jour tous les affichages attendus.
- Sa suppression ne laisse aucun objet orphelin.
- L'étape peut être ignorée.
- Toutes les redirections provisoires ont été supprimées.
- La suite complète de tests passe.
- Les migrations ont été testées depuis une copie représentative du schéma de production.

## 11. Critères d'acceptation finaux avant mise en production

Ces critères sont obligatoires uniquement lorsque les cinq lots sont intégrés.

### Inscription et validation

- [ ] L'inscription ne demande que l'e-mail et le mot de passe avec confirmation.
- [ ] L'utilisateur voit l'adresse à laquelle le message de validation a été envoyé.
- [ ] Un e-mail non vérifié ne permet pas l'accès aux données privées.
- [ ] Le renvoi de l'e-mail est protégé côté serveur contre les abus.
- [ ] Un lien de validation valide conduit à la prochaine étape réelle du parcours.
- [ ] Un lien invalide ou expiré affiche un message utile et une action de récupération.

### Profil

- [ ] Le pseudo est obligatoire et son usage est expliqué.
- [ ] L'anniversaire et la photo sont facultatifs et leur usage est expliqué.
- [ ] Seuls le jour et le mois d'anniversaire sont collectés.
- [ ] Le profil incomplet est reprenable après reconnexion.
- [ ] Le profil reste modifiable après l'onboarding.

### Groupe et invitations

- [ ] Un utilisateur peut créer un groupe, rejoindre avec un code ou remettre cette décision à plus tard.
- [ ] Une invitation survit à l'inscription, à la validation e-mail et à la configuration du profil.
- [ ] L'adhésion est confirmée par `POST` et est idempotente.
- [ ] Le lien d'invitation est non devinable et distinct du code court.
- [ ] Le créateur peut copier, partager et envoyer le lien par e-mail.
- [ ] La régénération invalide l'ancien lien.
- [ ] L'aperçu public ne révèle aucune donnée personnelle sur les membres.

### Personnes sans compte

- [ ] Le créateur peut ajouter zéro, une ou plusieurs personnes sans compte.
- [ ] Chaque personne apparaît immédiatement dans le groupe.
- [ ] Les membres autorisés peuvent gérer sa liste.
- [ ] La création et la suppression ne laissent aucun objet orphelin.
- [ ] L'interface n'utilise jamais les termes « faux compte » ou « fausse personne ».

### Qualité générale

- [ ] Le parcours fonctionne en français et en anglais.
- [ ] Le parcours principal fonctionne sur mobile et ordinateur.
- [ ] Toutes les actions sont accessibles au clavier et disposent de libellés compréhensibles.
- [ ] Aucun token, mot de passe ou e-mail n'est ajouté aux logs ou aux événements analytiques.
- [ ] La suite complète de tests automatisés passe.
- [ ] Les vérifications Django de déploiement ne signalent aucune nouvelle erreur.
- [ ] La migration depuis l'état de production et un retour arrière de procédure ont été répétés en environnement de validation.

## 12. Plan de tests

### Tests unitaires

- Résolution de la prochaine étape d'onboarding pour chaque combinaison d'état.
- Validation du formulaire d'inscription.
- Validation jour/mois de l'anniversaire.
- Génération et rotation des tokens d'invitation.
- Validation et déduplication des destinataires.
- Limitation des envois.
- Création transactionnelle d'une personne sans compte.

### Tests d'intégration Django

- Inscription → validation → profil → création de groupe.
- Inscription → validation → profil → rejoindre avec un code.
- Invitation → inscription → validation → profil → acceptation.
- Connexion d'un ancien compte déjà migré.
- Reprise après déconnexion à chaque étape.
- Invitation devenue invalide pendant le parcours.
- Utilisateur déjà membre.
- Rotation du lien d'invitation.
- Échec complet et échec partiel du backend e-mail.
- Ajout, renommage et suppression d'une personne sans compte.
- Contrôles d'accès entre membre et personne extérieure au groupe.

### Tests end-to-end prioritaires

1. nouvel utilisateur sans invitation ;
2. nouvel utilisateur invité ;
3. utilisateur existant invité ;
4. création d'un groupe, partage du lien et adhésion d'un second compte ;
5. création d'un groupe avec deux personnes sans compte ;
6. reprise du parcours sur mobile après ouverture de l'e-mail.

## 13. Migration et déploiement après le lot 5

### Avant déploiement

- Sauvegarder la base de données.
- Exécuter les migrations sur une copie récente de la production.
- Vérifier le nombre d'utilisateurs migrés vers l'onboarding version 1.
- Vérifier l'absence de `ManagedMember` orphelin et d'utilisateur géré sans profil associé ; prévoir une migration de réparation si nécessaire.
- Tester la configuration réelle d'envoi d'e-mails et les limites.
- Vérifier la construction des liens avec le domaine public et chaque préfixe de langue.

### Déploiement

- Déployer les cinq lots ensemble.
- Appliquer les migrations avant l'activation du nouveau code selon la stratégie habituelle du projet.
- Effectuer un test de fumée avec une nouvelle adresse e-mail et une invitation réelle.
- Surveiller les erreurs de validation d'e-mail, les boucles de redirection et les échecs d'envoi.

### Retour arrière

- La procédure de retour arrière doit privilégier le redéploiement applicatif compatible avec les nouveaux champs plutôt que la suppression immédiate de colonnes.
- Les nouveaux champs doivent être ajoutés de manière compatible avec l'ancien code lorsque cela est possible.
- La rotation ou la suppression de tokens ne doit pas être utilisée comme mécanisme de retour arrière.

## 14. Indicateurs de réussite

Les mesures suivantes peuvent être collectées sans donnée personnelle :

- inscription commencée et terminée ;
- e-mail validé ;
- profil terminé ;
- groupe créé, rejoint ou étape remise à plus tard ;
- invitation envoyée ;
- personne sans compte ajoutée ;
- délai médian entre inscription et fin d'onboarding ;
- taux d'abandon par étape ;
- taux d'échec technique d'envoi des e-mails.

Les tokens, adresses e-mail, pseudos, noms de groupes et noms de personnes ne doivent jamais faire partie de ces événements.

## 15. Hors périmètre global

- authentification sociale ;
- connexion sans mot de passe ;
- rôles complets au sein des groupes ;
- revendication d'une personne sans compte ;
- invitations individuelles avec suivi détaillé ;
- import d'un carnet d'adresses ;
- relances automatiques ;
- collecte de l'année de naissance ;
- refonte générale du tableau de bord ;
- modification du fonctionnement des listes événementielles et Secret Santa.

## 16. Définition de « terminé »

Le chantier est terminé lorsque :

1. les lots 1 à 5 sont fusionnés dans la même version candidate ;
2. tous les critères d'acceptation finaux sont satisfaits ;
3. la suite complète de tests est verte ;
4. les migrations ont été validées depuis l'état de production ;
5. les traductions, l'accessibilité et l'affichage mobile ont été vérifiés ;
6. la procédure de déploiement et de retour arrière est documentée ;
7. aucun écran, lien ou commentaire de code provisoire entre les lots ne subsiste.
