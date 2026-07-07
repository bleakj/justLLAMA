Name:           justllama
Version:        0.1.0
Release:        1%{?dist}
Summary:        Desktop GUI wrapper for llama.cpp on Fedora KDE Plasma
License:        LGPL-3.0-only
URL:            https://github.com/user/justllama
Source0:        %{name}-%{version}.tar.gz

BuildArch:      noarch
BuildRequires:  python3-devel >= 3.11
BuildRequires:  python3-setuptools >= 68.0
BuildRequires:  python3-wheel
BuildRequires:  python3-pyside6-devel >= 6.5
BuildRequires:  qt6-qtdeclarative-devel
BuildRequires:  kf6-kirigami-devel

Requires:       python3-pyside6 >= 6.5
Requires:       python3-requests >= 2.31
Requires:       python3-huggingface_hub >= 1.17
Requires:       kf6-kirigami
Recommends:     llama-cpp

%description
JustLlama provides a modern KDE Plasma desktop GUI for interacting with
locally-running large language models via llama.cpp's llama-server.
Features include model browsing, chat completion with streaming,
RAG (document ingestion and retrieval), and persistent agent memory.

%prep
%autosetup -n %{name}-%{version}

%build
%py3_build_wheel

%install
%py3_install_wheel %{name}-%{version}-*.whl

# Desktop file
mkdir -p %{buildroot}%{_datadir}/applications
cat > %{buildroot}%{_datadir}/applications/%{name}.desktop << EOF
[Desktop Entry]
Type=Application
Name=JustLlama
Comment=Desktop GUI for llama.cpp
Exec=python3 -m justllama
Icon=%{name}
Terminal=false
Categories=Utility;Development;AI;
EOF

# Icon (placeholder)
mkdir -p %{buildroot}%{_datadir}/icons/hicolor/256x256/apps
# Install a placeholder icon or leave for user to provide
touch %{buildroot}%{_datadir}/icons/hicolor/256x256/apps/%{name}.png

%files
%license LICENSE
%doc README.md
%{python3_sitelib}/%{name}/
%{python3_sitelib}/%{name}-%{version}.dist-info/
%{_datadir}/applications/%{name}.desktop
%{_datadir}/icons/hicolor/256x256/apps/%{name}.png

%changelog
* Mon Jul 07 2026 Aubrey <aubrey@example.com> - 0.1.0-1
- Initial package
- PySide6 + Kirigami QML UI
- llama-server lifecycle management
- Model browser and HuggingFace downloader
- RAG with ChromaDB vector store
- Persistent memory with SQLite + FTS5
