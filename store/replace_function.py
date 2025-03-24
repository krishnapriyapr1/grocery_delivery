import re

# Read the new function
with open('admin_suppliers_temp.py', 'r') as f:
    new_function = f.read()

# Read the original file
with open('views.py', 'r') as f:
    content = f.read()

# Create the pattern to match the old function
pattern = r'@login_required\s*@user_passes_test\(is_admin\)\s*def admin_suppliers\(request\).*?return render\(request, \'store/admin/suppliers.html\', context\)'

# Replace the old function with the new one
new_content = re.sub(pattern, new_function.strip(), content, flags=re.DOTALL)

# Write back to the file
with open('views.py', 'w') as f:
    f.write(new_content)
