class TR(object):
    __language__ = 'tr'
#----------------
#
# TEMEL
#
#----------------
    WELCOME_MSG = "Merhaba {}"
    DOWNLOADING = 'İndiriliyor........'
    DOWNLOAD_PROGRESS = """
<b>╭─ İlerleme
│
├ {0}
│
├ Tamamlandı : <code>{1} / {2}</code>
│
├ Başlık : <code>{3}</code>
│
╰─ Tür : <code>{4}</code></b>
"""
    UPLOADING = 'Yükleniyor........'
    ZIPPING = 'Arşivleniyor........'
    TASK_COMPLETED = "İndirme Tamamlandı"

#----------------
#
# AYARLAR PANELİ
#
#----------------
    INIT_SETTINGS_PANEL = '<b>Bot Ayarlarına Hoş Geldiniz</b>'
    LANGUAGE_PANEL = 'Buradan bot dilini seçin'
    CORE_PANEL = 'Ana ayarları buradan düzenleyin'
    PROVIDERS_PANEL = 'Her platformu ayrı ayrı yapılandırın'
    RCLONE_PANEL = '<b>Rclone Ayarları</b>'
    RCLONE_STATUS = 'Durum: {}'
    RCLONE = 'Rclone'
    RCLONE_UPLOAD_PATH = 'Yükleme Yolu: {}'
    RCLONE_REMOTE_BROWSE = '🗂️ Uzakları Gez'
    RCLONE_SET_UPLOAD_PATH = '📂 Yükleme Yolunu Ayarla'
    RCLONE_IMPORT_CONF = '📥 rclone.conf İçe Aktar'
    RCLONE_COPY = '📄 Bulut → Bulut Kopyala'
    RCLONE_MOVE = '📦 Bulut → Bulut Taşı'
    RCLONE_BACK = '🔙 Geri'
    RCLONE_SEND_CONF = 'Lütfen rclone.conf dosyanızı gönderin.'
    RCLONE_CONF_SAVED = '✅ rclone.conf kaydedildi.'
    RCLONE_DEST_SET = '✅ Yükleme yolu ayarlandı: {}'
    RCLONE_BROWSE_HEADER = '<b>Geziyorsunuz:</b> {}'
    RCLONE_BROWSE_NEXT = 'İleri ▶️'
    RCLONE_BROWSE_PREV = '◀️ Geri'
    RCLONE_BROWSE_UP = '⬆️ Yukarı'
    RCLONE_SELECT_THIS = 'Bu klasörü seç'
    RCLONE_PICK_SOURCE = 'Kaynak seç'
    RCLONE_PICK_DEST = 'Hedef seç'
    RCLONE_OP_IN_PROGRESS = 'İşlem çalışıyor...'
    RCLONE_OP_DONE = '✅ İşlem tamamlandı.'
    RCLONE_OP_FAILED = '❌ İşlem başarısız: {}'
    RCLONE_MOUNT = '🔗 Uzağı Bağla'
    RCLONE_UNMOUNT = '❌ Ayır (Unmount)'
    RCLONE_PICK_MOUNT = 'Bağlanacak uzak depoyu seçin'
    RCLONE_MOUNT_DONE = '✅ Bağlandı: {}'
    RCLONE_MOUNT_FAIL = '❌ Bağlama başarısız: {}'
    RCLONE_UNMOUNT_PICK = 'Ayırmak için bir bağlama noktası seçin'
    RCLONE_UNMOUNT_DONE = '✅ Ayrıldı: {}'
    RCLONE_UNMOUNT_FAIL = '❌ Ayırma başarısız: {}'
    RCLONE_NO_MOUNTS = 'Bağlı nokta bulunamadı.'
    RCLONE_DELETE_CONF = '🗑️ rclone.conf Sil'
    RCLONE_CONF_DELETED = '🗑️ rclone.conf silindi.'
    RCLONE_CONF_DELETE_FAILED = 'rclone.conf silinemedi'

    

    TELEGRAM_PANEL = """
<b>Telegram Ayarları</b>

Yöneticiler : {2}
Yetkili Kullanıcılar : {3}
Yetkili Sohbetler : {4}
"""
    BAN_AUTH_FORMAT = '/komut {userid} kullanın'
    BAN_ID = 'Banı kaldırıldı: {}'
    USER_DOEST_EXIST = "Bu ID mevcut değil"
    USER_EXIST = 'Bu ID zaten mevcut'
    AUTH_ID = 'Başarıyla Yetkilendirildi'

#----------------
#
# DÜĞMELER
#
#----------------
    MAIN_MENU_BUTTON = 'ANA MENÜ'
    CLOSE_BUTTON = 'KAPAT'
    PROVIDERS = 'HİZMETLER'
    TELEGRAM = 'Telegram'
    CORE = 'ÇEKİRDEK'
    


    BOT_PUBLIC = 'Bot Herkese Açık - {}'
    BOT_LANGUAGE = 'Dil'
    ANTI_SPAM = 'Spam Koruması - {}'
    LANGUAGE = 'Dil'
    QUALITY = 'Kalite'
    AUTHORIZATION = "Yetkilendirmeler"

    POST_ART_BUT = "Posterleri Gönder : {}"
    SORT_PLAYLIST = 'Çalma Listesini Sırala : {}'
    DISABLE_SORT_LINK = 'Sıralama Bağlantısını Devre Dışı Bırak : {}'
    PLAYLIST_CONC_BUT = "Çalma Listesi Toplu İndirme : {}"
    PLAYLIST_ZIP = 'Çalma Listesi Arşivle : {}'
    ARTIST_BATCH_BUT = 'Sanatçı Toplu Yükle : {}'
    ARTIST_ZIP = 'Sanatçı Arşivle : {}'
    ALBUM_ZIP = 'Albüm Arşivle : {}'





    RCLONE_LINK = 'Doğrudan Bağlantı'
    INDEX_LINK = 'Dizin Bağlantısı'

#----------------
#
# HATALAR
#
#----------------
    ERR_NO_LINK = 'Bağlantı bulunamadı :('
    ERR_LINK_RECOGNITION = "Üzgünüm, verilen bağlantı tanınamadı."



#----------------
#
# UYARILAR
#
#----------------


#----------------
#
# PARÇA & ALBÜM PAYLAŞIMLARI
#
#----------------
    ALBUM_TEMPLATE = """
🎶 <b>Başlık :</b> {title}
👤 <b>Sanatçı :</b> {artist}
📅 <b>Çıkış Tarihi :</b> {date}
🔢 <b>Toplam Parça :</b> {totaltracks}
📀 <b>Toplam Albüm :</b> {totalvolume}
💫 <b>Kalite :</b> {quality}
📡 <b>Sağlayıcı :</b> {provider}
🔞 <b>Açık İçerik :</b> {explicit}
"""

    PLAYLIST_TEMPLATE = """
🎶 <b>Başlık :</b> {title}
🔢 <b>Toplam Parça :</b> {totaltracks}
💫 <b>Kalite :</b> {quality}
📡 <b>Sağlayıcı :</b> {provider}
"""

    SIMPLE_TITLE = """
Adı : {0}
Türü : {1}
Sağlayıcı : {2}
"""

    ARTIST_TEMPLATE = """
👤 <b>Sanatçı :</b> {artist}
💫 <b>Kalite :</b> {quality}
📡 <b>Sağlayıcı :</b> {provider}
"""
