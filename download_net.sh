mkdir -p shared/networks
git clone https://github.com/OpenWaterAnalytics/EPANET.git
cp EPANET/example-networks/Net1.inp shared/networks/Net1.inp
cp EPANET/example-networks/Net2.inp shared/networks/Net2.inp
cp EPANET/example-networks/Net3.inp shared/networks/Net3.inp
rm -rf EPANET