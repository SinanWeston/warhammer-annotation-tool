# Phase 3 unit slugs cheatsheet

Covers all 24 factions present in the Phase 3 crop set. For factions marked
_missing from units.json_, use common sense snake_case slugs (e.g. `necron_warrior`,
`tactical_marine`) — if unsure, right-click the crop → "Search image with Google Lens".

Rules of thumb (same as before):
- Broader over specific when unsure (`intercessors` > `heavy_intercessors` if you can't tell)
- Aim for 2–4 crops per unit slug within each faction so auto_split has queries
- `notes` column is free-text for any ambiguity you want to flag

## tyranids (34 crops)

- `hive_tyrant` — Hive Tyrant
- `winged_hive_tyrant` — Winged Hive Tyrant
- `broodlord` — Broodlord
- `tyranid_prime` — Tyranid Prime
- `winged_tyranid_prime` — Winged Tyranid Prime
- `neurotyrant` — Neurotyrant
- `tervigon` — Tervigon
- `old_one_eye` — Old One Eye
- `deathleaper` — Deathleaper
- `parasite_of_mortrex` — Parasite of Mortrex
- `the_swarmlord` — The Swarmlord
- `termagants` — Termagants
- `hormagaunts` — Hormagaunts
- `gargoyles` — Gargoyles
- `genestealers` — Genestealers
- `neurogaunts` — Neurogaunts
- `ripper_swarms` — Ripper Swarms
- `barbgaunts` — Barbgaunts
- `tyranid_warriors_with_melee_bio-weapons` — Tyranid Warriors with Melee Bio-weapons
- `tyranid_warriors_with_ranged_bio-weapons` — Tyranid Warriors with Ranged Bio-weapons
- `tyrant_guard` — Tyrant Guard
- `hive_guard` — Hive Guard
- `zoanthropes` — Zoanthropes
- `venomthropes` — Venomthropes
- `von_ryans_leapers` — Von Ryan's Leapers
- `lictor` — Lictor
- `neurolictor` — Neurolictor
- `pyrovores` — Pyrovores
- `biovores` — Biovores
- `raveners` — Raveners
- `carnifexes` — Carnifexes
- `screamer-killer` — Screamer-killer
- `psychophage` — Psychophage
- `haruspex` — Haruspex
- `toxicrene` — Toxicrene
- `maleceptor` — Maleceptor
- `exocrine` — Exocrine
- `tyrannofex` — Tyrannofex
- `trygon` — Trygon
- `mawloc` — Mawloc
- `norn_emissary` — Norn Emissary
- `norn_assimilator` — Norn Assimilator
- `harpy` — Harpy
- `hive_crone` — Hive Crone
- `tyrannocyte` — Tyrannocyte
- `sporocyst` — Sporocyst
- `spore_mines` — Spore Mines
- `mucolid_spores` — Mucolid Spores
- `harridan` — Harridan
- `hierophant` — Hierophant
- `barbed_hierodule` — Barbed Hierodule
- `scythed_hierodule` — Scythed Hierodule
- `dimachaeron` — Dimachaeron

## adepta_sororitas (20 crops)

- `canoness` — Canoness
- `canoness_with_jump_pack` — Canoness with Jump Pack
- `palatine` — Palatine
- `morvenn_vahl` — Morvenn Vahl
- `saint_celestine` — Saint Celestine
- `junith_eruita` — Junith Eruita
- `triumph_of_saint_katherine` — Triumph of Saint Katherine
- `dialogus` — Dialogus
- `dogmata` — Dogmata
- `hospitaller` — Hospitaller
- `imagifier` — Imagifier
- `ministorum_priest` — Ministorum Priest
- `battle_sisters_squad` — Battle Sisters Squad
- `sisters_novitiate_squad` — Sisters Novitiate Squad
- `celestian_sacresants` — Celestian Sacresants
- `celestian_insidiants` — Celestian Insidiants
- `dominion_squad` — Dominion Squad
- `retributor_squad` — Retributor Squad
- `seraphim_squad` — Seraphim Squad
- `zephyrim_squad` — Zephyrim Squad
- `repentia_squad` — Repentia Squad
- `arco-flagellants` — Arco-Flagellants
- `sanctifiers` — Sanctifiers
- `paragon_warsuits` — Paragon Warsuits
- `penitent_engines` — Penitent Engines
- `mortifiers` — Mortifiers
- `sororitas_rhino` — Sororitas Rhino
- `immolator` — Immolator
- `exorcist` — Exorcist
- `castigator` — Castigator
- `repressor` — Repressor

## adeptus_mechanicus (20 crops)

- `tech-priest_dominus` — Tech-Priest Dominus
- `tech-priest_enginseer` — Tech-Priest Enginseer
- `tech-priest_manipulus` — Tech-Priest Manipulus
- `technoarcheologist` — Technoarcheologist
- `skitarii_marshal` — Skitarii Marshal
- `sydonian_skatros` — Sydonian Skatros
- `cybernetica_datasmith` — Cybernetica Datasmith
- `belisarius_cawl` — Belisarius Cawl
- `skitarii_rangers` — Skitarii Rangers
- `skitarii_vanguard` — Skitarii Vanguard
- `sicarian_infiltrators` — Sicarian Infiltrators
- `sicarian_ruststalkers` — Sicarian Ruststalkers
- `corpuscarii_electro-priests` — Corpuscarii Electro-Priests
- `fulgurite_electro-priests` — Fulgurite Electro-Priests
- `kataphron_breachers` — Kataphron Breachers
- `kataphron_destroyers` — Kataphron Destroyers
- `pteraxii_sterylizors` — Pteraxii Sterylizors
- `pteraxii_skystalkers` — Pteraxii Skystalkers
- `serberys_raiders` — Serberys Raiders
- `serberys_sulphurhounds` — Serberys Sulphurhounds
- `sydonian_dragoons` — Sydonian Dragoons
- `ironstrider_ballistarii` — Ironstrider Ballistarii
- `kastelan_robots` — Kastelan Robots
- `onager_dunecrawler` — Onager Dunecrawler
- `skorpius_disintegrator` — Skorpius Disintegrator
- `skorpius_dunerider` — Skorpius Dunerider
- `archaeopter_fusilave` — Archaeopter Fusilave
- `archaeopter_stratoraptor` — Archaeopter Stratoraptor
- `archaeopter_transvector` — Archaeopter Transvector
- `secutarii_hoplites` — Secutarii Hoplites
- `secutarii_peltasts` — Secutarii Peltasts

## black_templars (20 crops)

_Not in units.json — use common sense slugs (e.g. `black_warrior`)._

## chaos_daemons (20 crops)

- `beasts_of_nurgle` — Beasts of Nurgle
- `belakor` — Be'lakor
- `bloodcrushers` — Bloodcrushers
- `bloodletters` — Bloodletters
- `bloodmaster` — Bloodmaster
- `bloodthirster` — Bloodthirster
- `blue_horrors` — Blue Horrors
- `burning_chariot` — Burning Chariot
- `changecaster` — Changecaster
- `contorted_epitome` — Contorted Epitome
- `daemon_prince_of_chaos` — Daemon Prince of Chaos
- `daemon_prince_of_chaos_with_wings` — Daemon Prince of Chaos with Wings
- `daemonettes` — Daemonettes
- `epidemius` — Epidemius
- `exalted_flamer` — Exalted Flamer
- `fateskimmer` — Fateskimmer
- `fiends` — Fiends
- `flamers` — Flamers
- `flesh_hounds` — Flesh Hounds
- `fluxmaster` — Fluxmaster
- `great_unclean_one` — Great Unclean One
- `hellflayers` — Hellflayers
- `horticulous_slimux` — Horticulous Slimux
- `infernal_enrapturess` — Infernal Enrapturess
- `kairos_fateweaver` — Kairos Fateweaver
- `karanak` — Karanak
- `keeper_of_secrets` — Keeper of Secrets
- `lord_of_change` — Lord of Change
- `nurglings` — Nurglings
- `pink_horrors` — Pink Horrors
- `plague_drones` — Plague Drones
- `plaguebearers` — Plaguebearers
- `poxbringer` — Poxbringer
- `rendmaster_on_blood_throne` — Rendmaster on Blood Throne
- `rotigus` — Rotigus
- `screamers` — Screamers
- `seekers` — Seekers
- `shalaxi_helbane` — Shalaxi Helbane
- `skarbrand` — Skarbrand
- `skull_cannon` — Skull Cannon
- `skullmaster` — Skullmaster
- `skulltaker` — Skulltaker
- `sloppity_bilepiper` — Sloppity Bilepiper
- `soul_grinder` — Soul Grinder
- `spoilpox_scrivener` — Spoilpox Scrivener
- `syllesske` — Syll'esske
- `the_blue_scribes` — The Blue Scribes
- `the_changeling` — The Changeling
- `the_masque_of_slaanesh` — The Masque of Slaanesh
- `tormentbringer` — Tormentbringer
- `tranceweaver` — Tranceweaver
- `zarakynel` — Zarakynel

## chaos_knights (20 crops)

- `knight_abominant` — Knight Abominant
- `knight_desecrator` — Knight Desecrator
- `knight_despoiler` — Knight Despoiler
- `knight_rampager` — Knight Rampager
- `knight_tyrant` — Knight Tyrant
- `war_dog_brigand` — War Dog Brigand
- `war_dog_executioner` — War Dog Executioner
- `war_dog_huntsman` — War Dog Huntsman
- `war_dog_karnivore` — War Dog Karnivore
- `war_dog_stalker` — War Dog Stalker
- `chaos_cerastus_knight_lancer` — Chaos Cerastus Knight Lancer
- `chaos_cerastus_knight_acheron` — Chaos Cerastus Knight Acheron
- `chaos_cerastus_knight_castigator` — Chaos Cerastus Knight Castigator
- `chaos_cerastus_knight_atrapos` — Chaos Cerastus Knight Atrapos
- `chaos_questoris_knight_magaera` — Chaos Questoris Knight Magaera
- `chaos_questoris_knight_styrix` — Chaos Questoris Knight Styrix
- `chaos_acastus_knight_porphyrion` — Chaos Acastus Knight Porphyrion
- `chaos_acastus_knight_asterius` — Chaos Acastus Knight Asterius
- `war_dog_moirax` — War Dog Moirax

## custodes (20 crops)

_Not in units.json — use common sense slugs (e.g. `custodes_warrior`)._

## grey_knights (20 crops)

_Not in units.json — use common sense slugs (e.g. `grey_warrior`)._

## harlequins (20 crops)

- `death_jester` — Death Jester
- `shadowseer` — Shadowseer
- `solitaire` — Solitaire
- `skyweavers` — Skyweavers
- `starweaver` — Starweaver
- `troupe` — Troupe
- `troupe_master` — Troupe Master
- `voidweaver` — Voidweaver

## imperial_guard (20 crops)

_Not in units.json — use common sense slugs (e.g. `imperial_warrior`)._

## imperial_knights (20 crops)

- `canis_rex` — Canis Rex
- `knight_castellan` — Knight Castellan
- `knight_crusader` — Knight Crusader
- `knight_errant` — Knight Errant
- `knight_gallant` — Knight Gallant
- `knight_paladin` — Knight Paladin
- `knight_preceptor` — Knight Preceptor
- `knight_valiant` — Knight Valiant
- `knight_warden` — Knight Warden
- `armiger_warglaive` — Armiger Warglaive
- `armiger_helverin` — Armiger Helverin
- `cerastus_knight_lancer` — Cerastus Knight Lancer
- `cerastus_knight_acheron` — Cerastus Knight Acheron
- `cerastus_knight_castigator` — Cerastus Knight Castigator
- `cerastus_knight_atrapos` — Cerastus Knight Atrapos
- `questoris_knight_magaera` — Questoris Knight Magaera
- `questoris_knight_styrix` — Questoris Knight Styrix
- `acastus_knight_porphyrion` — Acastus Knight Porphyrion
- `acastus_knight_asterius` — Acastus Knight Asterius
- `armiger_moirax` — Armiger Moirax

## orks (20 crops)

- `warboss` — Warboss
- `warboss_in_mega_armour` — Warboss in Mega Armour
- `big_mek` — Big Mek
- `big_mek_in_mega_armour` — Big Mek in Mega Armour
- `big_mek_with_shokk_attack_gun` — Big Mek with Shokk Attack Gun
- `weirdboy` — Weirdboy
- `wurrboy` — Wurrboy
- `painboy` — Painboy
- `painboss` — Painboss
- `mek` — Mek
- `beastboss` — Beastboss
- `beastboss_on_squigosaur` — Beastboss on Squigosaur
- `deffkilla_wartrike` — Deffkilla Wartrike
- `ghazghkull_thraka` — Ghazghkull Thraka
- `mozrog_skragbad` — Mozrog Skragbad
- `boss_snikrot` — Boss Snikrot
- `zodgrod_wortsnagga` — Zodgrod Wortsnagga
- `boyz` — Boyz
- `beast_snagga_boyz` — Beast Snagga Boyz
- `gretchin` — Gretchin
- `nobz` — Nobz
- `meganobz` — Meganobz
- `kommandos` — Kommandos
- `stormboyz` — Stormboyz
- `tankbustas` — Tankbustas
- `burna_boyz` — Burna Boyz
- `lootas` — Lootas
- `flash_gitz` — Flash Gitz
- `breaka_boyz` — Breaka Boyz
- `squighog_boyz` — Squighog Boyz
- `warbikers` — Warbikers
- `deffkoptas` — Deffkoptas
- `trukk` — Trukk
- `battlewagon` — Battlewagon
- `deff_dread` — Deff Dread
- `killa_kans` — Killa Kans
- `gorkanaut` — Gorkanaut
- `morkanaut` — Morkanaut
- `stompa` — Stompa
- `hunta_rig` — Hunta Rig
- `kill_rig` — Kill Rig
- `mek_gunz` — Mek Gunz
- `boomdakka_snazzwagon` — Boomdakka Snazzwagon
- `kustom_boosta-blasta` — Kustom Boosta-blasta
- `megatrakk_scrapjet` — Megatrakk Scrapjet
- `rukkatrukk_squigbuggy` — Rukkatrukk Squigbuggy
- `shokkjump_dragsta` — Shokkjump Dragsta
- `blitza-bommer` — Blitza-bommer
- `burna-bommer` — Burna-bommer
- `dakkajet` — Dakkajet
- `wazbom_blastajet` — Wazbom Blastajet
- `mega_dread` — Mega Dread
- `meka-dread` — Meka-Dread
- `gargantuan_squiggoth` — Gargantuan Squiggoth
- `squiggoth` — Squiggoth
- `kill_krusha` — Kill Krusha
- `kill_tank` — Kill Tank
- `grot_tanks` — Grot Tanks
- `grot_mega-tank` — Grot Mega-tank
- `chinork_warkopta` — Chinork Warkopta
- `fighta-bommer` — Fighta-bommer
- `big_trakk` — Big Trakk

## tau_empire (20 crops)

- `cadre_fireblade` — Cadre Fireblade
- `ethereal` — Ethereal
- `commander_in_coldstar_battlesuit` — Commander in Coldstar Battlesuit
- `commander_in_enforcer_battlesuit` — Commander in Enforcer Battlesuit
- `commander_farsight` — Commander Farsight
- `commander_shadowsun` — Commander Shadowsun
- `darkstrider` — Darkstrider
- `kroot_flesh_shaper` — Kroot Flesh Shaper
- `kroot_trail_shaper` — Kroot Trail Shaper
- `kroot_war_shaper` — Kroot War Shaper
- `kroot_lone-spear` — Kroot Lone-Spear
- `firesight_team` — Firesight Team
- `strike_team` — Strike Team
- `breacher_team` — Breacher Team
- `pathfinder_team` — Pathfinder Team
- `stealth_battlesuits` — Stealth Battlesuits
- `crisis_battlesuits` — Crisis Battlesuits
- `crisis_fireknife_battlesuits` — Crisis Fireknife Battlesuits
- `crisis_starscythe_battlesuits` — Crisis Starscythe Battlesuits
- `crisis_sunforge_battlesuits` — Crisis Sunforge Battlesuits
- `broadside_battlesuits` — Broadside Battlesuits
- `ghostkeel_battlesuit` — Ghostkeel Battlesuit
- `riptide_battlesuit` — Riptide Battlesuit
- `stormsurge` — Stormsurge
- `kroot_carnivores` — Kroot Carnivores
- `kroot_farstalkers` — Kroot Farstalkers
- `kroot_hounds` — Kroot Hounds
- `krootox_riders` — Krootox Riders
- `krootox_rampagers` — Krootox Rampagers
- `vespid_stingwings` — Vespid Stingwings
- `devilfish` — Devilfish
- `hammerhead_gunship` — Hammerhead Gunship
- `sky_ray_gunship` — Sky Ray Gunship
- `piranhas` — Piranhas
- `razorshark_strike_fighter` — Razorshark Strike Fighter
- `sun_shark_bomber` — Sun Shark Bomber
- `taunar_supremacy_armour` — Ta'unar Supremacy Armour
- `tiger_shark` — Tiger Shark
- `manta` — Manta
- `barracuda` — Barracuda
- `rvarna_battlesuit` — R'varna Battlesuit
- `yvahra_battlesuit` — Y'vahra Battlesuit
- `xv9_hazard_battlesuits` — XV9 Hazard Battlesuits
- `remora_stealth_drones` — Remora Stealth Drones
- `tetras` — Tetras

## ynnari (20 crops)

- `yvraine` — Yvraine
- `the_visarch` — The Visarch
- `the_yncarne` — The Yncarne
- `ynnari_archon` — Ynnari Archon
- `ynnari_incubi` — Ynnari Incubi
- `ynnari_kabalite_warriors` — Ynnari Kabalite Warriors
- `ynnari_raider` — Ynnari Raider
- `ynnari_reavers` — Ynnari Reavers
- `ynnari_succubus` — Ynnari Succubus
- `ynnari_venom` — Ynnari Venom
- `ynnari_wyches` — Ynnari Wyches

## death_guard (19 crops)

_Not in units.json — use common sense slugs (e.g. `death_warrior`)._

## chaos_space_marines (18 crops)

- `abaddon_the_despoiler` — Abaddon the Despoiler
- `accursed_cultists` — Accursed Cultists
- `chaos_bikers` — Chaos Bikers
- `chaos_land_raider` — Chaos Land Raider
- `chaos_lord` — Chaos Lord
- `chaos_lord_in_terminator_armour` — Chaos Lord in Terminator Armour
- `chaos_lord_with_jump_pack` — Chaos Lord with Jump Pack
- `chaos_predator_annihilator` — Chaos Predator Annihilator
- `chaos_predator_destructor` — Chaos Predator Destructor
- `chaos_rhino` — Chaos Rhino
- `chaos_spawn` — Chaos Spawn
- `chaos_terminator_squad` — Chaos Terminator Squad
- `chaos_vindicator` — Chaos Vindicator
- `chosen` — Chosen
- `cultist_firebrand` — Cultist Firebrand
- `cultist_mob` — Cultist Mob
- `cypher` — Cypher
- `dark_apostle` — Dark Apostle
- `dark_commune` — Dark Commune
- `defiler` — Defiler
- `fabius_bile` — Fabius Bile
- `fellgor_beastmen` — Fellgor Beastmen
- `forgefiend` — Forgefiend
- `haarken_worldclaimer` — Haarken Worldclaimer
- `havocs` — Havocs
- `helbrute` — Helbrute
- `heldrake` — Heldrake
- `heretic_astartes_daemon_prince` — Heretic Astartes Daemon Prince
- `heretic_astartes_daemon_prince_with_wings` — Heretic Astartes Daemon Prince with Wings
- `huron_blackheart` — Huron Blackheart
- `khorne_berzerkers` — Khorne Berzerkers
- `khorne_lord_of_skulls` — Khorne Lord of Skulls
- `legionaries` — Legionaries
- `lord_discordant_on_helstalker` — Lord Discordant on Helstalker
- `master_of_executions` — Master of Executions
- `master_of_possession` — Master of Possession
- `masters_of_the_maelstrom` — Masters of the Maelstrom
- `maulerfiend` — Maulerfiend
- `nemesis_claw` — Nemesis Claw
- `noise_marines` — Noise Marines
- `obliterators` — Obliterators
- `plague_marines` — Plague Marines
- `raptors` — Raptors
- `red_corsairs_raiders` — Red Corsairs Raiders
- `red_corsairs_reave-captain` — Red Corsairs Reave-Captain
- `rubric_marines` — Rubric Marines
- `sorcerer` — Sorcerer
- `sorcerer_in_terminator_armour` — Sorcerer in Terminator Armour
- `terrax-pattern_termite` — Terrax-pattern Termite
- `traitor_enforcer` — Traitor Enforcer
- `traitor_guardsmen_squad` — Traitor Guardsmen Squad
- `vashtorr_the_arkifane` — Vashtorr the Arkifane
- `venomcrawler` — Venomcrawler
- `warp_talons` — Warp Talons
- `warpsmith` — Warpsmith

## genestealer_cult (18 crops)

_Not in units.json — use common sense slugs (e.g. `genestealer_warrior`)._

## deathwatch (13 crops)

_Not in units.json — use common sense slugs (e.g. `deathwatch_warrior`)._

## necrons (13 crops)

- `overlord` — Overlord
- `overlord_with_translocation_shroud` — Overlord with Translocation Shroud
- `catacomb_command_barge` — Catacomb Command Barge
- `chronomancer` — Chronomancer
- `plasmancer` — Plasmancer
- `psychomancer` — Psychomancer
- `technomancer` — Technomancer
- `hexmark_destroyer` — Hexmark Destroyer
- `skorpekh_lord` — Skorpekh Lord
- `lokhust_lord` — Lokhust Lord
- `royal_warden` — Royal Warden
- `lord` — Lord
- `illuminor_szeras` — Illuminor Szeras
- `imotekh_the_stormlord` — Imotekh the Stormlord
- `the_silent_king` — The Silent King
- `trazyn_the_infinite` — Trazyn the Infinite
- `orikan_the_diviner` — Orikan the Diviner
- `anrakyr_the_traveller` — Anrakyr the Traveller
- `nemesor_zahndrekh` — Nemesor Zahndrekh
- `vargard_obyron` — Vargard Obyron
- `transcendent_ctan` — Transcendent C'tan
- `ctan_shard_of_the_nightbringer` — C'tan Shard of the Nightbringer
- `ctan_shard_of_the_deceiver` — C'tan Shard of the Deceiver
- `ctan_shard_of_the_void_dragon` — C'tan Shard of the Void Dragon
- `necron_warriors` — Necron Warriors
- `immortals` — Immortals
- `lychguard` — Lychguard
- `deathmarks` — Deathmarks
- `flayed_ones` — Flayed Ones
- `triarch_praetorians` — Triarch Praetorians
- `cryptothralls` — Cryptothralls
- `skorpekh_destroyers` — Skorpekh Destroyers
- `ophydian_destroyers` — Ophydian Destroyers
- `lokhust_destroyers` — Lokhust Destroyers
- `lokhust_heavy_destroyers` — Lokhust Heavy Destroyers
- `canoptek_wraiths` — Canoptek Wraiths
- `canoptek_scarab_swarms` — Canoptek Scarab Swarms
- `canoptek_spyders` — Canoptek Spyders
- `canoptek_reanimator` — Canoptek Reanimator
- `canoptek_doomstalker` — Canoptek Doomstalker
- `tomb_blades` — Tomb Blades
- `triarch_stalker` — Triarch Stalker
- `ghost_ark` — Ghost Ark
- `doomsday_ark` — Doomsday Ark
- `annihilation_barge` — Annihilation Barge
- `night_scythe` — Night Scythe
- `doom_scythe` — Doom Scythe
- `monolith` — Monolith
- `obelisk` — Obelisk
- `tesseract_vault` — Tesseract Vault
- `convergence_of_dominion` — Convergence of Dominion
- `seraptek_heavy_construct` — Seraptek Heavy Construct
- `canoptek_acanthrites` — Canoptek Acanthrites
- `canoptek_tomb_sentinel` — Canoptek Tomb Sentinel
- `canoptek_tomb_stalker` — Canoptek Tomb Stalker
- `night_shroud` — Night Shroud
- `tesseract_ark` — Tesseract Ark
- `gauss_pylon` — Gauss Pylon
- `sentry_pylon` — Sentry Pylon

## eldar (12 crops)

_Not in units.json — use common sense slugs (e.g. `eldar_warrior`)._

## space_marines (9 crops)

- `captain` — Captain
- `captain_in_gravis_armour` — Captain in Gravis Armour
- `captain_in_phobos_armour` — Captain in Phobos Armour
- `captain_in_terminator_armour` — Captain in Terminator Armour
- `captain_with_jump_pack` — Captain with Jump Pack
- `chaplain` — Chaplain
- `chaplain_in_terminator_armour` — Chaplain in Terminator Armour
- `chaplain_on_bike` — Chaplain on Bike
- `chaplain_with_jump_pack` — Chaplain with Jump Pack
- `librarian` — Librarian
- `librarian_in_phobos_armour` — Librarian in Phobos Armour
- `librarian_in_terminator_armour` — Librarian in Terminator Armour
- `lieutenant` — Lieutenant
- `lieutenant_in_phobos_armour` — Lieutenant in Phobos Armour
- `lieutenant_in_reiver_armour` — Lieutenant in Reiver Armour
- `lieutenant_with_combi-weapon` — Lieutenant with Combi-weapon
- `techmarine` — Techmarine
- `ancient` — Ancient
- `ancient_in_terminator_armour` — Ancient in Terminator Armour
- `apothecary` — Apothecary
- `apothecary_biologis` — Apothecary Biologis
- `bladeguard_ancient` — Bladeguard Ancient
- `judiciar` — Judiciar
- `assault_intercessor_squad` — Assault Intercessor Squad
- `heavy_intercessor_squad` — Heavy Intercessor Squad
- `intercessor_squad` — Intercessor Squad
- `infernus_squad` — Infernus Squad
- `tactical_squad` — Tactical Squad
- `scout_squad` — Scout Squad
- `scout_sniper_squad` — Scout Sniper Squad
- `incursor_squad` — Incursor Squad
- `infiltrator_squad` — Infiltrator Squad
- `reiver_squad` — Reiver Squad
- `desolation_squad` — Desolation Squad
- `devastator_squad` — Devastator Squad
- `sternguard_veteran_squad` — Sternguard Veteran Squad
- `vanguard_veteran_squad` — Vanguard Veteran Squad
- `bladeguard_veteran_squad` — Bladeguard Veteran Squad
- `terminator_squad` — Terminator Squad
- `terminator_assault_squad` — Terminator Assault Squad
- `aggressor_squad` — Aggressor Squad
- `centurion_assault_squad` — Centurion Assault Squad
- `centurion_devastator_squad` — Centurion Devastator Squad
- `eradicator_squad` — Eradicator Squad
- `hellblaster_squad` — Hellblaster Squad
- `eliminator_squad` — Eliminator Squad
- `suppressor_squad` — Suppressor Squad
- `inceptor_squad` — Inceptor Squad
- `assault_squad` — Assault Squad
- `outrider_squad` — Outrider Squad
- `bike_squad` — Bike Squad
- `attack_bike_squad` — Attack Bike Squad
- `scout_bike_squad` — Scout Bike Squad
- `invader_atv` — Invader ATV
- `redemptor_dreadnought` — Redemptor Dreadnought
- `brutalis_dreadnought` — Brutalis Dreadnought
- `ballistus_dreadnought` — Ballistus Dreadnought
- `venerable_dreadnought` — Venerable Dreadnought
- `ironclad_dreadnought` — Ironclad Dreadnought
- `dreadnought` — Dreadnought
- `invictor_tactical_warsuit` — Invictor Tactical Warsuit
- `contemptor_dreadnought` — Contemptor Dreadnought
- `leviathan_dreadnought` — Leviathan Dreadnought
- `deredeo_dreadnought` — Deredeo Dreadnought
- `repulsor` — Repulsor
- `repulsor_executioner` — Repulsor Executioner
- `impulsor` — Impulsor
- `gladiator_lancer` — Gladiator Lancer
- `gladiator_reaper` — Gladiator Reaper
- `gladiator_valiant` — Gladiator Valiant
- `predator` — Predator
- `rhino` — Rhino
- `razorback` — Razorback
- `vindicator` — Vindicator
- `whirlwind` — Whirlwind
- `hunter` — Hunter
- `stalker` — Stalker
- `land_raider` — Land Raider
- `land_raider_crusader` — Land Raider Crusader
- `land_raider_redeemer` — Land Raider Redeemer
- `drop_pod` — Drop Pod
- `land_speeder` — Land Speeder
- `land_speeder_storm` — Land Speeder Storm
- `hammerfall_bunker` — Hammerfall Bunker
- `firestrike_servo-turrets` — Firestrike Servo-turrets
- `stormraven_gunship` — Stormraven Gunship
- `stormtalon_gunship` — Stormtalon Gunship
- `stormhawk_interceptor` — Stormhawk Interceptor
- `fire_raptor_gunship` — Fire Raptor Gunship
- `storm_eagle_gunship` — Storm Eagle Gunship
- `thunderhawk_gunship` — Thunderhawk Gunship
- `sicaran_battle_tank` — Sicaran Battle Tank
- `caestus_assault_ram` — Caestus Assault Ram
- `crusader_squad` — Crusader Squad
- `sword_brethren` — Sword Brethren
- `emperors_champion` — Emperor's Champion
- `high_marshal_helbrecht` — High Marshal Helbrecht
- `castellan` — Castellan
- `chaplain_grimaldus` — Chaplain Grimaldus
- `sanguinary_guard` — Sanguinary Guard
- `death_company_marines` — Death Company Marines
- `death_company_captain` — Death Company Captain
- `sanguinary_priest` — Sanguinary Priest
- `commander_dante` — Commander Dante
- `the_sanguinor` — The Sanguinor
- `lemartes` — Lemartes
- `mephiston` — Mephiston
- `deathwing_terminator_squad` — Deathwing Terminator Squad
- `deathwing_command_squad` — Deathwing Command Squad
- `ravenwing_black_knights` — Ravenwing Black Knights
- `ravenwing_dark_talon` — Ravenwing Dark Talon
- `ravenwing_darkshroud` — Ravenwing Darkshroud
- `azrael` — Azrael
- `belial` — Belial
- `sammael` — Sammael
- `lion_eljonson` — Lion El'Jonson
- `wulfen` — Wulfen
- `thunderwolf_cavalry` — Thunderwolf Cavalry
- `fenrisian_wolves` — Fenrisian Wolves
- `bjorn_the_fell-handed` — Bjorn the Fell-Handed
- `logan_grimnar` — Logan Grimnar
- `ragnar_blackmane` — Ragnar Blackmane
- `murderfang` — Murderfang
- `deathwatch_veterans` — Deathwatch Veterans
- `watch_master` — Watch Master

## thousand_sons (7 crops)

_Not in units.json — use common sense slugs (e.g. `thousand_warrior`)._

## drukhari (4 crops)

- `archon` — Archon
- `beastmaster` — Beastmaster
- `chronos` — Chronos
- `court_of_the_archon` — Court of the Archon
- `drazhar` — Drazhar
- `grotesques` — Grotesques
- `haemonculus` — Haemonculus
- `hellions` — Hellions
- `incubi` — Incubi
- `kabalite_warriors` — Kabalite Warriors
- `lady_malys` — Lady Malys
- `lelith_hesperax` — Lelith Hesperax
- `mandrakes` — Mandrakes
- `raider` — Raider
- `raven_strike_fighter` — Raven Strike Fighter
- `ravager` — Ravager
- `razorwing_jetfighter` — Razorwing Jetfighter
- `reavers` — Reavers
- `scourges` — Scourges
- `succubus` — Succubus
- `talos` — Talos
- `tantalus` — Tantalus
- `urien_rakarth` — Urien Rakarth
- `venom` — Venom
- `voidraven_bomber` — Voidraven Bomber
- `wyches` — Wyches
