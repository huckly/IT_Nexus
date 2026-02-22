import unittest
from unittest.mock import patch, MagicMock

# 預先 Mock 日誌以避免導入時失敗 (因為導入時會執行 setup_logging)
with patch('utils.setup_logging', return_value=MagicMock()):
    from scripts.sync_librenms_to_netbox import get_manufacturer_name
    from scripts.sync_netbox_to_glpi import ROLE_TO_ENDPOINT

class TestSyncLogic(unittest.TestCase):

    def test_manufacturer_mapping(self):
        """測試 LibreNMS OS 到 NetBox Manufacturer 的對照邏輯。"""
        # 情境 1：已知 OS
        self.assertEqual(get_manufacturer_name({'os': 'ios'}), 'Cisco')
        self.assertEqual(get_manufacturer_name({'os': 'fortios'}), 'Fortinet')
        
        # 情境 2：未知 OS，但有 Hardware 資訊
        self.assertEqual(get_manufacturer_name({'os': 'unknown', 'hardware': 'Dell PowerEdge'}), 'Dell')
        
        # 情境 3：完全未知
        self.assertEqual(get_manufacturer_name({'os': None, 'hardware': None}), 'Unknown')

    def test_glpi_role_mapping(self):
        """測試 NetBox Role 到 GLPI 資產類型的對照。"""
        self.assertEqual(ROLE_TO_ENDPOINT.get('server'), 'Computer')
        self.assertEqual(ROLE_TO_ENDPOINT.get('switch'), 'NetworkEquipment')
        self.assertEqual(ROLE_TO_ENDPOINT.get('printer'), 'Printer')
        self.assertIsNone(ROLE_TO_ENDPOINT.get('non-existent-role'))

if __name__ == '__main__':
    unittest.main()
