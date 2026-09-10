# Diagnostic guard for generated fixtures ONLY. Does not edit Codex configuration.
# Called from Python; no administrator terminal is required.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$AccessSection = [System.Security.AccessControl.AccessControlSections]::Access
$Snapshot = [System.Collections.Generic.List[object]]::new()

function Write-Result($value) {
    [Console]::Out.WriteLine(($value | ConvertTo-Json -Depth 10 -Compress))
}

function Restore-Entries($entries) {
    $errors = [System.Collections.Generic.List[string]]::new()
    # Restore parents before children, then restore each child's exact saved DACL.
    foreach ($entry in @($entries | Sort-Object { $_.path.Length })) {
        try {
            $acl = Get-Acl -LiteralPath $entry.path
            $acl.SetSecurityDescriptorSddlForm($entry.sddl, $AccessSection)
            Set-Acl -LiteralPath $entry.path -AclObject $acl
        } catch {
            $errors.Add("Restore failed: $($entry.path): $($_.Exception.Message)")
        }
    }
    return ,$errors.ToArray()
}

try {
    $request = [Console]::In.ReadToEnd() | ConvertFrom-Json
    if ($request.action -notin @('install', 'restore')) { throw 'Unknown ACL action.' }
    $root = [IO.Path]::GetFullPath([string]$request.root).TrimEnd('\', '/')
    $rootItem = Get-Item -LiteralPath $root -Force
    if (-not $rootItem.PSIsContainer -or $rootItem.Name -notlike 'webinar-boundary-*') {
        throw 'Only a generated webinar-boundary-* directory may be used.'
    }
    if (($rootItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw 'Reparse-point fixture roots are not supported.'
    }
    $marker = [IO.Path]::Combine($root, '.webinar-fixture-id')
    if ([IO.File]::ReadAllText($marker).Trim() -ne [string]$request.fixture_id) {
        throw 'Fixture identity mismatch.'
    }
    if ([string]$request.fixture_id -notmatch '^[a-f0-9]{32}$') { throw 'Invalid fixture identity.' }

    $paths = if ($request.action -eq 'install') { @($request.paths) } else {
        @($request.snapshot | ForEach-Object { $_.path })
    }
    if ($paths.Count -eq 0) { throw 'No fixture paths supplied.' }
    foreach ($path in $paths) {
        $full = [IO.Path]::GetFullPath([string]$path)
        if (-not $full.StartsWith($root + '\', [StringComparison]::OrdinalIgnoreCase)) {
            throw 'Refusing to change an ACL outside the fixture tree.'
        }
        $relative = $full.Substring($root.Length + 1)
        $top = ($relative -split '[\\/]')[0]
        if ($top -notin @('author', 'judge', 'arbiter')) {
            throw 'Only role fixture trees may receive ACL changes.'
        }
        $node = Get-Item -LiteralPath $full -Force
        while ($node.FullName -ne $root) {
            if (($node.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw 'Reparse points are not supported in fixture paths.'
            }
            $parentPath = [IO.Path]::GetDirectoryName($node.FullName)
            if (-not $parentPath) { throw 'Invalid fixture ancestry.' }
            $node = Get-Item -LiteralPath $parentPath -Force
        }
    }

    if ($request.action -eq 'restore') {
        $failures = Restore-Entries $request.snapshot
        if ($failures.Count -gt 0) { throw ($failures -join '; ') }
        Write-Result @{status='RESTORED'; restored=$paths.Count}
        exit 0
    }

    # Resolve the EXISTING local group used by Codex 0.153.4; never create accounts.
    $account = [System.Security.Principal.NTAccount]::new([Environment]::MachineName, 'CodexSandboxUsers')
    $sid = $account.Translate([System.Security.Principal.SecurityIdentifier])
    $identity = [System.Security.Principal.WindowsIdentity]::GetCurrent()
    if ($identity.User.Value -eq $sid.Value -or
        @($identity.Groups | Where-Object { $_.Value -eq $sid.Value }).Count -ne 0) {
        throw 'Operator belongs to the denied group. Refusing to apply ACLs.'
    }

    # Capture every DACL BEFORE modifying any path.
    foreach ($path in $paths) {
        $acl = Get-Acl -LiteralPath $path
        if (-not $acl.AreAccessRulesCanonical) { throw "Noncanonical DACL: $path" }
        $Snapshot.Add(@{path=[string]$path; sddl=$acl.GetSecurityDescriptorSddlForm($AccessSection)})
    }
    # Set a DIRECT deny on each object, not just an inherited parent-directory deny.
    # No inheritable rules are added by this helper. Existing grants are preserved.
    $rule = [System.Security.AccessControl.FileSystemAccessRule]::new(
        $sid, [System.Security.AccessControl.FileSystemRights]::FullControl,
        [System.Security.AccessControl.InheritanceFlags]::None,
        [System.Security.AccessControl.PropagationFlags]::None,
        [System.Security.AccessControl.AccessControlType]::Deny)
    foreach ($path in @($paths | Sort-Object { $_.Length } -Descending)) {
        $acl = Get-Acl -LiteralPath $path
        $acl.AddAccessRule($rule)
        Set-Acl -LiteralPath $path -AclObject $acl
        $actual = Get-Acl -LiteralPath $path
        $rules = $actual.GetAccessRules($true, $false, [System.Security.Principal.SecurityIdentifier])
        $found = @($rules | Where-Object {
            $_.IdentityReference.Value -eq $sid.Value -and -not $_.IsInherited -and
            $_.AccessControlType -eq [System.Security.AccessControl.AccessControlType]::Deny -and
            (($_.FileSystemRights -band [System.Security.AccessControl.FileSystemRights]::FullControl) -eq
                [System.Security.AccessControl.FileSystemRights]::FullControl)
        })
        if ($found.Count -eq 0 -or -not $actual.AreAccessRulesCanonical) {
            throw "Direct deny verification failed: $path"
        }
    }
    Write-Result @{status='INSTALLED'; target_group='CodexSandboxUsers'; snapshot=@($Snapshot.ToArray())}
} catch {
    $message = $_.Exception.Message
    $rollbackErrors = @()
    if ($Snapshot.Count -gt 0) { $rollbackErrors = Restore-Entries $Snapshot.ToArray() }
    Write-Result @{status='ERROR'; error=$message; rollback_errors=@($rollbackErrors)}
    exit 1
}
