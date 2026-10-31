#!/usr/bin/env python3
"""
Fix nodriver package encoding issue
Automatically locates and fixes the network.py file
"""

import os
import sys
import site

def fix_nodriver():
    # Find the nodriver package location
    site_packages = site.getsitepackages()
    network_py_path = None
    
    for sp in site_packages:
        potential_path = os.path.join(sp, 'nodriver', 'cdp', 'network.py')
        if os.path.exists(potential_path):
            network_py_path = potential_path
            break
    
    if not network_py_path:
        # Try user site-packages
        user_site = site.getusersitepackages()
        potential_path = os.path.join(user_site, 'nodriver', 'cdp', 'network.py')
        if os.path.exists(potential_path):
            network_py_path = potential_path
    
    if not network_py_path:
        print("❌ Error: Could not find nodriver package installation")
        print("   Make sure nodriver is installed: pip install nodriver")
        return False
    
    print(f"📁 Found network.py at: {network_py_path}")
    
    try:
        # Read the file with error handling
        with open(network_py_path, 'rb') as f:
            content = f.read()
        
        # Decode with error handling, replacing problematic characters
        content_str = content.decode('utf-8', errors='replace')
        
        # Fix the specific line - replace the problematic character
        # The \xb1 character (±) should be properly handled
        content_str = content_str.replace('JSON (�Inf)', 'JSON (Infinity or -Infinity)')
        content_str = content_str.replace('±Inf', 'Infinity or -Infinity')
        content_str = content_str.replace('�', '+/-')
        
        # Add encoding declaration at the top if not present
        if '# -*- coding: utf-8 -*-' not in content_str.split('\n')[0]:
            lines = content_str.split('\n')
            lines.insert(0, '# -*- coding: utf-8 -*-')
            content_str = '\n'.join(lines)
        
        # Write back with UTF-8 encoding
        with open(network_py_path, 'w', encoding='utf-8') as f:
            f.write(content_str)
        
        print("✅ Successfully fixed network.py!")
        print("   You can now run your script.")
        return True
        
    except PermissionError:
        print("❌ Permission denied!")
        print("   Solution:")
        if sys.platform == 'win32':
            print("   → Run this script as Administrator")
            print("   → Or run: pip uninstall nodriver && pip install nodriver")
        else:
            print("   → Run with sudo: sudo python3 fix_nodriver.py")
        return False
    except Exception as e:
        print(f"❌ Error fixing file: {e}")
        return False

if __name__ == "__main__":
    print("🔧 nodriver Package Fix Tool\n")
    success = fix_nodriver()
    if success:
        print("\n✨ All done! Try running your script again.")
    else:
        print("\n💡 Alternative solution: pip uninstall nodriver && pip install nodriver")
